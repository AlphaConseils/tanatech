{
    "name": "TANATECH Theme",
    "description": "Custom website theme for TANATECH",
    "category": "Theme/Website",
    "version": "18.0.1.0.0",
    "author": "A.Maximilien",
    "depends": [
        "website",
    ],
    "data": [
        "data/generate_primary_template.xml",
        "views/layout.xml",
        "views/snippets.xml",
    ],
    "assets": {
        # "web.assets_frontend": [
        #     "tanatech_theme/static/src/scss/primary_variables.scss",
        #     # "tanatech_theme/static/src/css/custom_header.css",
        # ],
        "web._assets_primary_variables": [
            "tanatech_theme/static/src/scss/primary_variables.scss",
            "tanatech_theme/static/src/scss/responsive_header.scss",
        ],
        "web.assets_frontend": [
            "tanatech_theme/static/src/core/emoji_picker.scss",
        ],
        "website.assets_wysiwyg": [
            "tanatech_theme/static/src/js/options.js",
        ],
    },
    "license": "LGPL-3",
}
