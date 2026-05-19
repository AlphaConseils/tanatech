from odoo import models, fields, api

def number_in_words_ariary(number):
    units = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
             'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept',
             'dix-huit', 'dix-neuf']
    tens = ['', 'dix', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante',
            'soixante', 'quatre-vingt', 'quatre-vingt']

    def convert_below_1000(n):
        if n == 0:
            return ''
        elif n < 20:
            return units[n]
        elif n < 100:
            ten = n // 10
            unit = n % 10
            if ten == 7:
                return 'soixante-' + units[10 + unit]
            elif ten == 9:
                return 'quatre-vingt-' + units[10 + unit]
            elif ten == 8:
                return 'quatre-vingt' + ('-' + units[unit] if unit else 's')
            else:
                if unit == 1:
                    return tens[ten] + '-et-un'
                elif unit == 0:
                    return tens[ten]
                else:
                    return tens[ten] + '-' + units[unit]
        else:
            cent = n // 100
            reste = n % 100
            if cent == 1:
                prefix = 'cent'
            else:
                prefix = units[cent] + ' cent'
            if reste == 0:
                return prefix + ('s' if cent > 1 else '')
            else:
                return prefix + ' ' + convert_below_1000(reste)

    def convert(n):
        if n == 0:
            return 'zéro'
        elif n < 0:
            return 'moins ' + convert(-n)

        parts = []
        milliards = n // 1_000_000_000
        millions = (n % 1_000_000_000) // 1_000_000
        milliers = (n % 1_000_000) // 1_000
        reste = n % 1_000

        if milliards:
            parts.append(convert_below_1000(milliards) + ' milliard' + ('s' if milliards > 1 else ''))
        if millions:
            parts.append(convert_below_1000(millions) + ' million' + ('s' if millions > 1 else ''))
        if milliers:
            if milliers == 1:
                parts.append('mille')
            else:
                parts.append(convert_below_1000(milliers) + ' mille')
        if reste:
            parts.append(convert_below_1000(reste))

        return ' '.join(parts)

    ariary = round(number)
    return (convert(ariary) + ' ariary').capitalize()


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    amount_in_words = fields.Char(
        string='Amount in words',
        compute='_compute_amount_in_words',
        store=True,
    )

    @api.depends('amount_total')
    def _compute_amount_in_words(self):
        for record in self:
            record.amount_in_words = number_in_words_ariary(record.amount_total)