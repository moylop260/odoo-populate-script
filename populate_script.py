# pylint: disable=undefined-variable
# flake8: noqa

# Disable all base_automation for faster improve

import logging
import random
import string
from concurrent.futures import ThreadPoolExecutor

from odoo import SUPERUSER_ID, api
from odoo.tests import Form

_logger = logging.getLogger(__name__)
context_no_mail = {
    "mail_create_nosubscribe": True,  # At create or message_post, do not subscribe the current user to the record thread
    "mail_auto_subscribe_no_notify": True,  # Do no notify users set as followers of the mail thread
    "mail_create_nolog": True,  # At create, do not log the automatic ‘<Document> created’ message
    "lang": False,
}


def generate_random_name(length=8):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def create_partner(env2):
    with Form(env2["res.partner"]) as partner_form:
        random_name = generate_random_name()
        partner_form.name = f"Partner {random_name}"
        partner_form.email = f"{random_name.lower()}@example.com"
        partner_form.phone = f"555-000-{random.randint(1000, 9999)}"
    partner = partner_form.save()
    return partner


def create_order(env2, partner_id, product_id):
    partner = env2["res.partner"].browse(partner_id)
    product = env2["product.product"].browse(product_id)
    with Form(env2["sale.order"]) as order_form:
        order_form.partner_id = partner
        with order_form.order_line.new() as line:
            line.product_id = product
            line.product_uom_qty = 1
            line.price_unit = 100.0
    order = order_form.save()
    return order


def reassing_orders(orders, partner_id):
    # orders.mapped("partner_id")
    _logger.info("Re-assinging orders %s to partner %s", orders, partner_id)
    orders.with_context(**context_no_mail).write({"partner_id": partner_id})
    orders.env.cr.commit()
    # _logger.info("Deleting dummy partners %s", partners)
    # partners.unlink()


def create_order_thread(product_id, top_partner_id, sale_order_base_id):
    with env.registry.cursor() as cr:
        env2 = api.Environment(cr, SUPERUSER_ID, context_no_mail)

        _logger.info("Creating partner...")
        # partner_id = create_partner(env2).id
        top_partner = env2["res.partner"].browse(top_partner_id)
        partner = top_partner.copy({"vat": False})  # vat False to avoid raising extra constraints
        _logger.info("...created partner_id %s", partner)
        _logger.info("Creating order")
        # order = create_order(env2, partner.id, product_id)
        order = env2["sale.order"].browse(sale_order_base_id).copy({"partner_id": partner.id})
        _logger.info("...created order_id %s", order.id)
        env2.cr.commit()


def create_threads(workers, num_orders):
    top_product_id = env["sale.order.line"].read_group(
        [], ["product_id"], ["product_id"], orderby="product_id_count desc", limit=1, lazy=True
    )[0]["product_id"][0]
    top_partner_id = env["res.partner"].search([], order="customer_rank DESC", limit=1).id
    max_partner_id = env["res.partner"].search([], order="id DESC", limit=1).id
    sale_order_base = create_order(env, top_partner_id, top_product_id)
    env.cr.commit()
    _logger.info(
        "Top sales partner %s max partner id %s sale order base %s", top_partner_id, max_partner_id, sale_order_base
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for _ in range(num_orders):
            future = executor.submit(create_order_thread, top_product_id, top_partner_id, sale_order_base.id)
            futures.append(future)

        for future in futures:
            future.result()

    # Assign all the order to same partner in this point because of avoid concurrent update for computed store=True in partner
    # new_sale_orders = env["sale.order"].search([("partner_id", ">", max_partner_id)])
    # reassing_orders(new_sale_orders, top_partner_id)


def reassing_order_generic(limit=80):
    """Use this method directly in odoo shell in order to clean-up process unfinished"""
    top_partner_id = env["res.partner"].search([], order="customer_rank DESC", limit=1).id
    partners_duplicated_ids = env["res.partner"].read_group(
        [], ["name", "id:array_agg"], ["name"], orderby="name_count desc", limit=1
    )[0]["id"]
    # partners_duplicated_ids = sorted(partners_duplicated_ids)
    orders = env["sale.order"].search([("partner_id", "in", partners_duplicated_ids)], limit=limit)
    reassing_orders(orders, top_partner_id)
    delete_partners(partners_duplicated_ids, limit=limit)


def delete_partners(partners_duplicated_ids, limit=80):
    partners_with_sales_ids = (
        env["sale.order"].search([("partner_id", "in", partners_duplicated_ids)]).mapped("partner_id").ids
    )
    partners_duplicated_without_sales_ids = list(set(partners_duplicated_ids) - set(partners_with_sales_ids))
    partners = env["res.partner"].search(
        [("id", "in", partners_duplicated_without_sales_ids)], order="id", limit=limit
    )
    _logger.info("partner to delete %s", partners)
    partners.unlink()
    env.cr.commit()


# max workers supported in my laptop 60 and memory supported 100k orders
create_threads(workers=60, num_orders=100000)
