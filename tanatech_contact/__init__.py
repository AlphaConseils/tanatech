# -*- coding: utf-8 -*-

from . import models


# def post_init_hook(env):
#     """ Create a client code sequence for every existing company """
#     for company in env["res.company"].search([]):
#         company._ensure_client_code_sequence()