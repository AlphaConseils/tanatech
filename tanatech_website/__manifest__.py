{
    "name": "TANATECH Website",
    "description": "Custom website for TANATECH",
    "category": "Website",
    "version": "18.0.1.0.0",
    "author": "A.Maximilien",
    "depends": ["base", "website_sale", "auth_oauth"],
    "data": [
        "views/assistance.xml",
        "data/website_page.xml",
        "views/login.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            # "tanatech_website/static/src/scss/web_loging.scss",
            "tanatech_website/static/src/**/*",
        ],
    },
    "license": "LGPL-3",
}
