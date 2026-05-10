import constants as app_constants


def all_boards():
    return list(app_constants.BOARD_CONFIGS.keys())


def group_for_board(board_name):
    return app_constants.BOARD_CONFIGS.get(board_name, {}).get("group", app_constants.BOARD_GROUP_FLASH)


def operations_for_board(board_name):
    if group_for_board(board_name) == app_constants.BOARD_GROUP_PRODUCTION:
        return [app_constants.OPERATION_FLASH, app_constants.OPERATION_TEST]
    return [app_constants.OPERATION_FLASH]
