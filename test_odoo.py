import xmlrpc.client
import os

url = 'http://localhost:8069'
db = 'admin'
username = 'admin'
password = os.getenv('ODOO_PASSWORD', 'admin')

common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))

fields = models.execute_kw(db, uid, password, 'res.users', 'fields_get', [], {'attributes': ['string', 'help', 'type']})
print("groups_id in fields:", "groups_id" in fields)
