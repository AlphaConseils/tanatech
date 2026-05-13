# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.tools.translate import code_translations


# class Home(WebHome):
#     @http.route(route='/web/login', type='http', auth="none")
#     def web_login(self, redirect=None, **kw):
#         """Override web_login function to add features of this module."""
#         ensure_db()
#         request.params['login_success'] = False
#         if request.httprequest.method == 'GET' and redirect and request.session.uid:
#             return request.redirect(redirect)
#         if request.session.uid is None:
#             # no user -> auth=public with specific website public user
#             request.env["ir.http"]._auth_method_public()
#         else:
#             # auth=user
#             request.update_env(user=request.session.uid)
#         values = {val: item for val, item in request.params.items() if
#                   val in SIGN_UP_REQUEST_PARAMS}
#         try:
#             values['databases'] = http.db_list()
#         except odoo.exceptions.AccessDenied:
#             values['databases'] = None
#         if request.httprequest.method == 'POST':
#             old_uid = request.update_env(user=request.session.uid)
#             try:
#                 credential = {'login': request.params['login'], 'password': request.params['password'],
#                               'type': 'password'}
#                 uid = request.session.authenticate(request.session.db, credential)
#                 request.params['login_success'] = True
#                 return request.redirect(
#                     self._login_redirect(uid, redirect=redirect))
#             except odoo.exceptions.AccessDenied as e:
#                 request.update_env = old_uid
#                 if e.args == odoo.exceptions.AccessDenied().args:
#                     values['error'] = _("Wrong login/password")
#                 else:
#                     values['error'] = e.args[0]
#         else:
#             if 'error' in request.params and request.params.get(
#                     'error') == 'access':
#                 values['error'] = _(
#                     'Only employees can access this database. '
#                     'Please contact the administrator.')
#         if 'login' not in values and request.session.get('auth_login'):
#             values['login'] = request.session.get('auth_login')
#         if not odoo.tools.config['list_db']:
#             values['disable_database_manager'] = True
#         conf_param = request.env['ir.config_parameter'].sudo()
#         image = conf_param.get_param('tanatech_website.image')
#         url = conf_param.get_param('tanatech_website.url')
#         background_type = conf_param.get_param('tanatech_website.background')
#         if background_type == 'color':
#             values['bg'] = ''
#             values['color'] = conf_param.sudo().get_param(
#                 'tanatech_website.color')
#         elif background_type == 'image':
#             exist_rec = request.env['ir.attachment'].sudo().search(
#                 [('is_background', '=', True)])
#             if exist_rec:
#                 exist_rec.unlink()
#             attachments = request.env['ir.attachment'].sudo().create({
#                 'name': 'Background Image',
#                 'datas': image,
#                 'type': 'binary',
#                 'mimetype': 'image/png',
#                 'public': True,
#                 'is_background': True
#             })
#             base_url = conf_param.sudo().get_param('web.base.url')
#             url = base_url + '/web/image?' + 'model=ir.attachment&id=' + str(
#                 attachments.id) + '&field=datas'
#             values['bg_img'] = url or ''
#         elif background_type == 'url':
#             pre_exist = request.env['ir.attachment'].sudo().search(
#                 [('url', '=', url)])
#             if not pre_exist:
#                 attachments = request.env['ir.attachment'].sudo().create({
#                     'name': 'Background Image URL',
#                     'url': url,
#                     'type': 'url',
#                     'public': True
#                 })
#             else:
#                 attachments = pre_exist
#             encode = hashlib.md5(
#                 pycompat.to_text(attachments.url).encode("utf-8")).hexdigest()[
#                      0:7]
#             encode_url = "/web/image/{}-{}".format(attachments.id, encode)
#             values['bg_img'] = encode_url or ''
#         response = request.render("website.login_layout", values)
#         response.headers['X-Frame-Options'] = 'DENY'
#         return response


class WebsiteProduct(http.Controller):

    def _t(self, source):
        """Translate using the website's default language.

        _() from odoo uses a thread-local set at request start and cannot be
        overridden mid-request for a different lang. We read directly from the
        code_translations cache (loaded from the module's .po file) so that
        labels are always returned in the website's configured language,
        regardless of the visiting user's account language.
        """
        lang_code = request.website.default_lang_id.code
        try:
            trans = code_translations.get_python_translations("tanatech_website", lang_code)
            return trans.get(source) or source
        except Exception:
            return source

    @http.route("/get_product_categories", auth="public", type="json", website=True)
    def get_product_category(self):
        """Get the website categories for the snippet."""
        public_categs = (
            request.env["product.public.category"]
            .sudo()
            .search_read(
                [("parent_id", "=", False)], fields=["name", "id"], limit=8
            )
        )
        return {
            "categories": public_categs,
            "labels": {
                "categories": self._t("Categories"),
                "discoverSelection": self._t("Discover our selection of reliable solar solutions."),
                "seeAll": self._t("See all"),
                "defaultImage": self._t("Default image"),
            },
        }

    @http.route("/get_new_products", auth="public", type="json", website=True)
    def get_new_products(self):
        data = (
            request.env["product.template"]
            .sudo()
            .search_read(
                [("is_published", "=", True), ("sale_ok", "=", True)],
                fields=["name", "list_price", "product_variant_ids", "write_date"],
                limit=8,
            )
        )
        currency = request.env.company.currency_id
        products = []
        for tmpl in data:
            variant_ids = tmpl.get("product_variant_ids") or []
            products.append({
                "id": variant_ids[0] if variant_ids else tmpl["id"],
                "template_id": tmpl["id"],
                "name": tmpl["name"],
                "list_price": tmpl["list_price"],
                "write_date": tmpl["write_date"].isoformat() if tmpl.get("write_date") else "",
            })
        return {
            "products": products,
            "currency_symbol": currency.symbol,
            "currency_position": currency.position,
            "labels": {
                "newProducts": self._t("New products"),
                "discoverNew": self._t("Discover our new solar kits"),
                "seeAll": self._t("See all"),
                "addToCart": self._t("Add to cart"),
                "newBadge": self._t("New"),
                "removeOne": self._t("Remove one"),
                "addOne": self._t("Add one"),
                "defaultImage": self._t("Default image"),
            },
        }

    @http.route("/get_promotional_products", auth="public", type="json", website=True)
    def get_promotional_products(self):
        data = (
            request.env["product.template"]
            .sudo()
            .search_read(
                [
                    ("is_published", "=", True),
                    ("sale_ok", "=", True),
                    ("compare_list_price", ">", 0),
                ],
                fields=["name", "list_price", "compare_list_price", "product_variant_ids", "write_date"],
                limit=8,
            )
        )
        currency = request.env.company.currency_id
        products = []
        for tmpl in data:
            variant_ids = tmpl.get("product_variant_ids") or []
            price = tmpl["list_price"]
            compare_price = tmpl["compare_list_price"]
            discount = round((compare_price - price) / compare_price * 100) if compare_price > price else 0
            products.append({
                "id": variant_ids[0] if variant_ids else tmpl["id"],
                "template_id": tmpl["id"],
                "name": tmpl["name"],
                "list_price": price,
                "compare_list_price": compare_price,
                "discount": discount,
                "write_date": tmpl["write_date"].isoformat() if tmpl.get("write_date") else "",
            })
        return {
            "products": products,
            "currency_symbol": currency.symbol,
            "currency_position": currency.position,
            "labels": {
                "ourPromotionalOffers": self._t("Our promotional offers"),
                "discoverDiscounted": self._t("Discover our discounted solar kits"),
                "seeAll": self._t("See all"),
                "addToCart": self._t("Add to cart"),
                "removeOne": self._t("Remove one"),
                "addOne": self._t("Add one"),
                "defaultImage": self._t("Default image"),
            },
        }

    # @http.route("/get_home_slide", type="json", auth="public", website=True)
    # def get_home_slide(self):
    #     slides = (
    #         request.env["website.slider.image"]
    #         .sudo()
    #         .search_read(
    #             [("website_published", "=", True)],
    #             fields=["title", "image", "id", "note"],
    #         )
    #     )

    #     return {
    #         "images": slides,
    #     }
