class ParseError(Exception):
    """ to be raised in case of an invalid command """


class ItemNotFoundError(Exception):
    """ to be raised if a variable reference was not found """
