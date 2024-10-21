import random
import string
from concurrent.futures import ThreadPoolExecutor
from odoo.tests import Form
from odoo.exceptions import UserError
from odoo import api, SUPERUSER_ID


def generate_random_name(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def create_partners_and_orders(num_partners, num_orders):
    with env.registry.cursor() as cr:
        env2 = api.Environment(cr, SUPERUSER_ID, {})
        product = env2['product.product'].search([], limit=1)
        for _ in range(num_partners):
            with Form(env2['res.partner']) as partner_form:
                random_name = generate_random_name()
                partner_form.name = f'Partner {random_name}'
                partner_form.email = f'{random_name.lower()}@example.com'
                partner_form.phone = f'555-000-{random.randint(1000, 9999)}'
            partner = partner_form.save()
            env2.cr.commit()
            
            # Crear las órdenes de venta para el partner recién creado
            for _ in range(num_orders):
                with Form(env2['sale.order']) as order_form:
                    order_form.partner_id = partner
                    with order_form.order_line.new() as line:
                        line.product_id = product
                        line.product_uom_qty = 1
                        line.price_unit = 100.0
                order_form.save()
                env2.cr.commit()


partners_per_thread = 400
orders_per_thread = 2000

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = []
    for _ in range(5):
        future = executor.submit(create_partners_and_orders, partners_per_thread, orders_per_thread)
        futures.append(future)

    for future in futures:
        future.result()
