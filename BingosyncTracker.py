# start listening for score updates in bingosync room and output them to .txt files, spawned from interface
# also standarises OBS layout creation process
# takes 1-10 arguments: player1_color, player2_color...

import time, sys, shutil
import signal
from pathlib import Path
from selenium import webdriver
from selenium.common.exceptions import *
from selenium.webdriver.common.keys import Keys

js_script = """// callback function argument
                var done = arguments[0];

                // listen for any change in player list
                // this includes: join/leave, score updated, switched team/color
                $("#players-panel").on('DOMSubtreeModified',function(){
                // callback to python
                    done("foo")
                })
            """

track_lines = False
#List with the colors that are being used currently
colors = []

#List with current scores
scores = []

#Paths.
executing_path = Path.cwd()
obs_path = executing_path.joinpath("OBS")
#Save the paths for deletion 
obs_images_paths = []

bingosync_path = executing_path.joinpath("Bingosync")
driver = None





def get_selector(this_color):
    """Returns css selector for goalcount of a color"""
    return (f"span.goalcounter.{this_color}square")


def get_output_path(this_player):
    """Returns .txt output path for player"""

    return bingosync_path.joinpath("Scores", f"p{this_player + 1}.txt")



def output(this_player, value):
    """outputs score for player into a txt"""

    with open(get_output_path(this_player), "w+") as txt_file:
       txt_file.write(value)
       print(f"  * P{this_player + 1} score updated to {value}")
       txt_file.close()


def update_score(this_player, value):
    """Updates score of player this_player to value"""
    scores[this_player] = value
    output(this_player, value)


def read_sync_score(this_player):
    """Attempts to read out bingosync score for this_player, returns old score if player can't be found"""
    this_score = scores[this_player]
    this_color = colors[this_player]
    try:
        # give out current value
        value = driver.find_element_by_css_selector(get_selector(this_color)).find_element_by_class_name("squarecounter").get_attribute("innerHTML")
        if track_lines:
            value += driver.find_element_by_css_selector(get_selector(this_color)).find_element_by_class_name("rowcounter").get_attribute("innerHTML")
        return value
    except NoSuchElementException:
        # default condition: return old value
        return this_score


def full_read(player_count):
    """Reads every score and updates them if different"""

    for ind,score in enumerate(scores):
        temp_score = read_sync_score(ind)
        if score != temp_score:
            update_score(ind,temp_score)

def initialize_driver():
    """Opens a web browser to interact with bingosync with. Prefers Firefox to Chrome, dies if neither is available"""

    #attempt firefox
    global driver;

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
       print(str(bingosync_path.joinpath("chromedriver.exe")))
       driver = webdriver.Chrome(executable_path= bingosync_path.joinpath("chromedriver.exe"), options=opt)
       driver.set_script_timeout(1800)
       return driver
    except Exception:
       print ("Both Firefox and Chrome failed to launch (Are you missing chromedriver/geckodriver?)")
       return None

#TODO videos
def generate_OBS_images(background_image):
    """Makes copies of the colours players will use as color1, color2, etc so that OBS sets it up automatically. Also layout images"""
    try:
        for ind,color in enumerate(colors):
            obs_images_paths.append(path := obs_path.joinpath(f"color{ind+1}.png"))
            shutil.copy(bingosync_path.joinpath("Colours",f"{color}.png"), path)

            #Copy the background
        obs_images_paths.append(path := obs_path.joinpath(f"bg.png"))
        shutil.copy(obs_path.joinpath("Backgrounds", "Pictures", f"{background_image}.png"), path)
        #Copy the layout 
        obs_images_paths.append(path := obs_path.joinpath(f"outlinecolor.png"))
        shutil.copy(obs_path.joinpath("Colours", f"{background_image}.png"), path)
        return True
    except FileNotFoundError as e:
        print("A file wasn't found. The exception text is below.")
        print(e)
        print("Note that the listener is still running")
        return False

def delete_copies():
    for path in obs_images_paths:
        path.unlink()




def ctrlC_handler(signum, frame):
    print("\n >> Ending driver")
    print("Note that the image copies made won't be deleted")
    driver.quit()
    exit(-1)


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
        # check if color picker is present
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


    #This is terrible but I'm too lazy to refactor oddo's code to not use everything global. Maybe eventually.
    global colors;
    global scores;
    global track_lines;

    colors = [color.lower() for color in sys.argv[1:]]


    if not colors or len(colors) > 10:
       print ("Please, call the program with one to ten bingosync colors as parameters (For example: \"listener.py red blue\")")
       exit(-1)

    for color in colors:
       scores.append("0")

    #OBS input section
    bg_image = input(">> Please introduce the name of the image you wish to use as OBS background: ")
    track_lines = input(">> Is the row/line counter relevant to the score? [Y/N]: ").lower() == "y"
    # input room data
    room_nick   = "BingoTracker"
    room_url    = input(">>  Input room URL: ")
    room_pw     = input(">>  Input password: ")

    driver = initialize_driver()
    if driver == None:
       exit(-1)

    #set up for exiting the driver in case of CTRL+C interrupt
    signal.signal(signal.SIGINT, ctrlC_handler)

    if not attempt_login(driver,room_url, room_pw):
        exit(-1)
   
    # feedback
    for ind,color in enumerate(colors):
       print(f">>  P{ind + 1} -> " + color)

    print(">>  Close browser to stop")

    # update scores with a full read (in case of tracker disconnect)
    full_read(len(colors))

    generate_OBS_images(bg_image)

    while True:
        try:
            # waits for event
            driver.execute_async_script(js_script)
            print("   * Event occurred")
            # checks if bingosync scores were updated, if so write new scores to .txt
            full_read(len(colors))
        except (NoSuchWindowException, TimeoutException, WebDriverException) as e:
            driver.quit()
            break


    # exit
    delete_copies()

    print(">>  Listener terminated")
    print(">>  Press CTRL+C to exit")





Main()