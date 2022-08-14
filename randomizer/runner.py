from typing import List
import win32.win32gui as gui
import win32com.client as the_client
import win32api as api
import pywintypes

import time
import random

from randomizer.utils import check_for_active_handles, get_all_handles, filter_handles_by_exe_name, write_to_file

# Dictionary that maps keyboard-keys to their API represented signals
BUTTON_TO_KEY = {
    "LMB": 0x01,
    "RMB": 0x02,
    "Space": 0x20,
    "Esc": 0x1B,
}

# This is probably really hacky. This GLOBAL will be overwritten at the
# start of the main execution.
HANDLE_TO_NAME = {}


def choose_games_prompt(scummvm_handles: List, choose_all: bool = False) -> List:
    """Creates a list of all handles that belong to ScummVM games, and makes
    the user choose a sublist of at least two.
    Args:
        scummvm_handles (List): list of handles belonging to ScummVM
        choose_all (bool): for debugging only, choose all windows
    Returns:
        chosen_handles (List): list of hadles of the chosen games."""
    if choose_all:
        return scummvm_handles
    chosen_handles = []
    choice = ""

    # Opening prompt with abort option
    while choice in ["", "n"]:
        choice = input("Dear user, would you like to select games? [y]/n\n")
        if choice == "":
            choice = "y"
        if choice == "":
            return None

    # Selection of games, with abort option
    choice = ""
    while choice in ["", "n", "0"]:

        window_selection_string = "Please select one of these windows"
        window_selection_string += " to add to the rando:\n"
        window_selection_string += "0) I have selected all the games\n"

        # Listing all game names that haven't been chosen yet
        for i, item in enumerate(scummvm_handles, start=1):
            window_name = gui.GetWindowText(item)
            window_selection_string += f"{i}) {window_name}\n"
        choice = input(window_selection_string)
        if choice == "0":
            return chosen_handles
        try:
            int_choice = int(choice)
        except ValueError:
            continue
        if int_choice <= i:
            # Adding to chosen handles
            chosen_handles.append(scummvm_handles[int_choice - 1])
            print(
                f"""you have chosen {
                    gui.GetWindowText(scummvm_handles[int_choice - 1])
                    }"""
            )
            # removing from list of options
            scummvm_handles.remove(scummvm_handles[int_choice - 1])
            choice = input("press enter to choose next game. type 'y' to end.")
            if i == 1 or choice == "y":
                return chosen_handles

        # Choice invalid
        print("Invalid choice, please try again\n")


def random_runner(
    chosen_list: List,
    min: int = None,
    max: int = None,
    remove_current_game: bool = None,
    mode: str = None,
):
    """Randomly resetting loop. Chooses random next game to display. Time until
    next reset is randomly chosen between min and max seconds.
    Args:
        chosen_list (List): list of handles belonging the chosen games.
        min (int): minimal number of seconds before window switch
        max (int): maximal number of seconds before window switch
        remove_current_game (bool): forbids to remain in the same game.
        mode (str): "seconds" or "clicks"
    """
    # Setting non-default values via prompts
    if mode is None:
        mode_selection_string = "Please select mode: \nrandom time: [seconds]"
        mode_selection_string += "\nrandom clicks: clicks\n"
        mode = input(mode_selection_string)
        if mode != "clicks":
            mode = "seconds"
    if min is None:
        min = int(input(f"minimum number of {mode} on the same game?"))
    if max is None:
        max = int(input(f"maximum number of {mode} on the same game?"))
    if remove_current_game is None:
        remove_current_game = not bool(
            input("Do you allow staying in the same game? (default = n)")
        )
    shell = the_client.Dispatch("WScript.Shell")
    # Start with first entry on list
    current_handle = chosen_list[0]
    shell.SendKeys("%")
    gui.SetForegroundWindow(current_handle)
    # closing windows removes them from chosen list.
    # next game initialized for check_alive
    next_game = current_handle
    while len(chosen_list) > 1:
        if mode == "seconds":
            # get time for random sleeps.
            float_random = random.uniform(min, max)

            time.sleep(float_random)
        elif mode == "clicks":
            click_limit = random.choice(range(min, max + 1))
            num_of_clicks = 0
            while click_limit > 0:
                game_exe = str(gui.GetWindowText(current_handle))
                info_string = str(num_of_clicks) + "\n Current game: " + game_exe
                write_to_file(info_string, "clicks.txt")
                window_closed = wait_for_click(num_of_clicks, next_game)
                click_limit -= 1
                num_of_clicks += 1
                # force reroll if window was closed
                if window_closed:
                    chosen_list.remove(next_game)
                    print(f"Warning, game {next_game} was closed.")
                    click_limit = 0
        else:

            raise Exception("invalid mode")
        # using a sliced copy of all games to modify later.
        active_game_list = chosen_list[:]
        # Optionally removing current game.
        if remove_current_game and (current_handle in active_game_list):
            active_game_list.remove(current_handle)
        # TODO: check_window_validity(active_game_list)
        next_game = random.choice(active_game_list)
        # next_game_unavailabe = bool(check_for_active_handles([next_game]))
        print(next_game)
        # required to fix a bug with active windows.
        # Maybe better solutions exist.
        shell.SendKeys("%")
        current_handle = next_game
        # Choose next window, start over.
        try:
            gui.SetForegroundWindow(next_game)
        except pywintypes.error:
            chosen_list.remove(next_game)
            print(f"Warning, game {next_game} was closed.")
    while len(chosen_list) == 1:
        # very lazy way of checking that the window is still open
        print(f"Final Game {next_game} is still running.")
        time.sleep(1)
        try:
            gui.SetForegroundWindow(chosen_list[0])
        except pywintypes.error:
            chosen_list.remove(chosen_list[0])
            print(f"Final Game {next_game} was closed.")
    print("randomizer run ended successfully")


def wait_for_click(
    num_of_clicks: int, current_handle: int, list_of_buttons: list = ["LMB", "RMB", "Space", "Esc"]
):
    """Checks every button in the list for occurring presses. Can handle mutiple
    buttons held during press.
    Arguments:
    num_of_clicks (int): number of clicks since last randomization
    list_of_buttons (list): list of buttons that need to be observed.
    Returns:
        True, if window closed, False if not
    """
    # Instantiate arrays where each position represents a key. Keeping track of
    # Idle state and pressed state.
    n = len(list_of_buttons)
    idle_list = [True] * n
    if num_of_clicks == 0:
        idle_list = [False] * n
    pressed_list = [False] * n
    click_not_occured = True
    while click_not_occured:
        # Check that window is still active
        if bool(check_for_active_handles([current_handle])):
            return True

        # get actual values from buttons
        state_list = [api.GetKeyState(BUTTON_TO_KEY[key]) for key in BUTTON_TO_KEY]

        # test for idle buttons
        for index in range(n):
            if state_list[index] > -1:
                idle_list[index] = True

        # test for buttons pressed after being idle
        for index in range(n):
            if idle_list[index]:
                if state_list[index] < 0:
                    pressed_list[index] = True

        # test for buttons released after being pressed
        for index in range(n):
            if pressed_list[index]:
                if state_list[index] > -1:
                    click_not_occured = False
        # Wait for update
        time.sleep(0.001)
    return False

def check_window_validity(active_game_list):
    pass


if __name__ == "__main__":
    """Acutal execution. Obtains all handles, filters to get the ones
    from ScummVM, prompts user to choose, starts random_runner."""
    debug = False
    # Defaults
    choose_all = False
    if debug:
        choose_all = True

    list_of_all_handles = get_all_handles()
    scummvm_handles, handles_dict = filter_handles_by_exe_name(list_of_all_handles)
    HANDLE_TO_NAME = handles_dict
    chosen_list = choose_games_prompt(scummvm_handles, choose_all=choose_all)
    if len(chosen_list) < 2:
        raise Exception("need 2 games at least")
    print(chosen_list)
    if debug:
        random_runner(chosen_list, mode = "clicks", min = 3, max = 5)
    else: random_runner(chosen_list)
