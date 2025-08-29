{
    "name": "TANATECH Theme",
    "description": "Custom website theme for TANATECH",
    "category": "Theme/Website",
    "version": "18.0.1.0.0",
    "author": "A.Maximilien",
    "depends": ["website",],
    "data": [
        "data/generate_primary_template.xml",
        "views/layout.xml",
        "views/snippets.xml",
    ],
    "assets": {
        # "web.assets_frontend": [
        #     "theme_tanatech/static/src/scss/primary_variables.scss",
        #     # "theme_tanatech/static/src/css/custom_header.css",
        # ],
        "web._assets_primary_variables": [
            "theme_tanatech/static/src/scss/primary_variables.scss",
        ],
        "web.assets_frontend": [
            "theme_tanatech/static/src/core/emoji_picker.scss",
        ],
        "website.assets_wysiwyg": [
            "theme_tanatech/static/src/js/options.js",
        ],
    },
    "license": "LGPL-3",
}
