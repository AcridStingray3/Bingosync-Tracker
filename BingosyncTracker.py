# start listening for score updates in bingosync room and output them to .txt files, spawned from interface
# also standardises OBS layout creation process
# takes 1-10 arguments: player1_colour, player2_colour...

import time, sys, shutil, os, string
from pathlib import *
import signal
from selenium import webdriver
from selenium.common.exceptions import *
from selenium.webdriver.common.keys import Keys

js_script = """// callback function argument
                var done = arguments[0];

                // listen for any change in player list
                // this includes: join/leave, score updated, switched team/colour
                $("#players-panel").on('DOMSubtreeModified',function(){
                // callback to python
                    done("foo")
                })
            """

#Paths.
executing_path = Path.cwd()
obs_path = executing_path.joinpath("OBS")
#Save the paths for deletion 
obs_images_paths = []
bingosync_path = executing_path.joinpath("Bingosync")






def get_selector(this_colour):
    """Returns css selector for goalcount of a colour"""

    return (f"span.goalcounter.{this_colour}square")


def get_output_path(this_player):
    """Returns .txt output path for player"""

    return bingosync_path.joinpath("Scores", f"p{this_player + 1}.txt")


def output(this_player, value):
    """Outputs score for this_player into a txt"""

    with open(get_output_path(this_player), "w+") as txt_file:
       txt_file.write(value)
       print(f"     * P{this_player + 1} score updated to {value}")
       txt_file.close()


def update_score(this_player, value, scores):
    """Updates score of player this_player to value"""

    scores[this_player] = value
    output(this_player, value)


def read_bingosync_score(driver, colour, old_score, track_lines):
    """Attempts to read out bingosync score for this_player, returns old score if player can't be found"""

    try:
        # give out current value
        value = driver.find_element_by_css_selector(get_selector(colour)).find_element_by_class_name("squarecounter").get_attribute("innerHTML")
        if track_lines:
            value += driver.find_element_by_css_selector(get_selector(colour)).find_element_by_class_name("rowcounter").get_attribute("innerHTML")
        return value
    except NoSuchElementException:
        # default condition: return old value
        return old_score


def full_read(driver, scores, colours, track_lines):
    """Reads every score and updates them if different"""

    for ind, (colour, score) in enumerate(zip(colours, scores)):
        temp_score = read_bingosync_score(driver, colour, score, track_lines)
        if score != temp_score:
            update_score(ind, temp_score, scores)


def initialize_driver():
    """Opens a web browser to interact with bingosync with. Prefers Firefox to Chrome, dies if neither is available"""

    #attempt firefox
    try: 
        opt = webdriver.FirefoxOptions()
        opt.add_argument('-private')
        driver = webdriver.Firefox(executable_path=bingosync_path.joinpath("geckodriver.exe"), options=opt)
        driver.set_script_timeout(1800)
        return driver
    except Exception as e:
       pass

    # attempt Chrome
    try:
       opt = webdriver.ChromeOptions()
       opt.add_argument('--ignore-certificate-errors')
       opt.add_argument('--incognito')
       driver = webdriver.Chrome(executable_path= bingosync_path.joinpath("chromedriver.exe"), options=opt)
       driver.set_script_timeout(1800)
       return driver
    except Exception:
       print ("Both Firefox and Chrome failed to launch (Are you missing chromedriver/geckodriver?)")
       return None


def request_valid_input(str, list):
    """Asks user question str with options list, returns input if valid, prompts to ask again if not"""

    ans = string.capwords(input(str + f" {list}: "))
    if ans not in list:
        retry = input("No option chosen. Try again? [Y/N]: ").lower()
        if retry == "y":
            request_valid_input(str, list)
        else:
            print("Prompt skipped, continuing...")
            return ""
    else:
        print(f"Option '{ans}' selected.")
        return ans


def ow_symlink(src, dst):
    """Creates a symlink dst pointing to src whether dst already exists or not"""

    name = dst.name
    parent = dst.parent
    temp = parent.joinpath(f"temp_{name}")
    temp.unlink(missing_ok=True)
    os.symlink(src, temp)
    temp.replace(dst)


def generate_OBS_media(background_media, bg_type, fmt, colours):
    """Makes copies of the colours players will use as colour1, colour2, etc so that OBS sets it up automatically. Also layout image/video"""

    try:
        for ind,colour in enumerate(colours):
            obs_images_paths.append(path := obs_path.joinpath(f"colour{ind+1}.png"))
            ow_symlink(bingosync_path.joinpath("Colours",f"{colour}.png"), path)

        #Copy the background
        ow_symlink(obs_path.joinpath("Backgrounds", f"{bg_type}s", f"{background_media}.{fmt}"), path := obs_path.joinpath(f"bg.{fmt}"))
        obs_images_paths.append(path)
        #Copy the corresponding layout colour
        ow_symlink(obs_path.joinpath("Colours", f"{bg_type}s", f"{background_media}.png"), path := obs_path.joinpath("outlinecolour.png"))
        obs_images_paths.append(path)
        return True
    except FileNotFoundError as e:
        print(f">>  A file wasn't found, probably the OBS background {bg_type.lower()}.")
        return False


def delete_copies():
    """Removes all symlinks in OBS folder"""

    for path in obs_images_paths:
        path.unlink(missing_ok=True)


def delete_bg(path):
    """Removes symlinks to the background media in path"""

    files = [file for file in path.iterdir() if file.is_symlink() and file.stem == "bg"]
    for bg in files:
        if bg.suffix == ".png" or bg.suffix == ".mkv":
            bg.unlink()


def attempt_login(driver,url,pw):
    """Logs into the given bingosync room"""

    print(">>  Attempting login")
    driver.get(url)
    driver.find_element_by_id("id_player_name").send_keys("BingoTracker")     # input nickname
    driver.find_element_by_id("id_passphrase").send_keys(pw)                  # input password
    driver.find_element_by_id("id_is_spectator").send_keys(Keys.SPACE)        # join as spectator

    # attempt login
    driver.find_element_by_class_name("form-control").submit()                # submit login
    time.sleep(3)                                                             # firefox fails here if you don't wait a bit
    try:
        # check if colour picker is present
        driver.find_element_by_xpath("/html/body/div[1]/div[2]/div[1]/div/div[1]")
        print(">>  Logged in, listening with:")
        return True
    except NoSuchElementException:
        # login failed if not
        driver.quit()
        print(">>  Login failed")
        return False



def Main():
    # -------------------------------------------------------------------------------------------------------------------- #
    # start script


    colours = [colour.lower() for colour in sys.argv[1:]]

    scores = []

    if len(colours) > 10:
        print ("Please, call the program with up to ten bingosync colours as parameters (For example: \"BingoTracker.py red blue\")")
        os.exit(-1)

    if len(colours) == 0:
        print("No arguments were provided. Entering OBS only mode")


    for colour in colours:
        if colour not in ["orange", "red", "blue", "green", "purple", "navy", "teal", "brown", "pink", "yellow"]:
           print(f"{colour} is not a valid bingosync colour. Please, call the script with valid colours")
           os.exit(-1)

        scores.append("0")


    #OBS input section
    bg_type = request_valid_input(">>  Which background format would you like to use?", ["Video", "Image"])
    if len(bg_type) == 0:
        print(">>  Note that the bingosync listener is still running")
    else:
        if bg_type == "Video":
            fmt = "mkv"
            delfmt = "png"
        if bg_type == "Image":
            fmt = "png"
            delfmt = "mkv"
        bg_path = obs_path.joinpath("Backgrounds", f"{bg_type}s")
        bg_choices = [os.path.splitext(os.path.split(bg)[1])[0] for bg in os.scandir(bg_path)]
        bg_media = request_valid_input(f">>  Which background {bg_type.lower()} would you like to use?", bg_choices)
        if len(bg_media) == 0:
            print(">>  Note that the bingosync listener is still running")
        else:
            delete_bg(obs_path)
            if generate_OBS_media(bg_media, bg_type, fmt, colours):
                print(">>  OBS layout was created.")
            if len(colours) == 0:
                print(">>  Exiting...")
                os.exit(-1)

    
    track_lines = input(">>  Is the row/line counter relevant to the score? [Y/N]: ").lower() == "y"
    # input room data
    room_nick   = "BingoTracker"
    room_url    = input(">>  Input room URL: ")
    room_pw     = input(">>  Input password: ")

    driver = initialize_driver()
    if driver == None:
        os.exit(-1)


    if not attempt_login(driver,room_url, room_pw):
        os.exit(-1)


    # feedback
    for ind,colour in enumerate(colours):
        print(f">>  P{ind + 1} -> " + colour)


    print(">>  Close browser to stop")

        # update scores with a full read (in case of tracker disconnect)
    full_read(driver, scores, colours, track_lines)



    while True:
        try:
            # waits for event
            driver.execute_async_script(js_script)
            print("    * Event occurred")
            # checks if bingosync scores were updated, if so write new scores to .txt
            full_read(driver, scores, colours, track_lines)
        except (NoSuchWindowException, TimeoutException, WebDriverException) as e:
            driver.quit()
            break


    # os.exit
    delete_copies()

    print(">>  Listener terminated")
    print(">>  Press CTRL+C to exit")





Main()