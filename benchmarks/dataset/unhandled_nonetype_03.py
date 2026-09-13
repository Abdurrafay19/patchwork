def get_shipping_city(order):
    return order["shipping"]["address"]["city"]
