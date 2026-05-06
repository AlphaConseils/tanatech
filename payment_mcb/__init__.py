# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Activate MCB provider after install."""
    pass


def uninstall_hook(env):
    """Archive MCB provider on uninstall."""
    env['payment.provider'].search([('code', '=', 'mcb')]).write({'active': False})
