# start listening for score updates in bingosync room and output them to .txt files, spawned from interface
# also standardises OBS layout creation process
# takes 1-10 arguments: player1_colour, player2_colour...


import time, sys, shutil, os, string
import tkinter as tk
import elevate
from tkinter import W, E, Label, Radiobutton, Entry, Checkbutton, Button, Grid, IntVar, BooleanVar, StringVar
from pathlib import *
import signal
from selenium import webdriver
from selenium.common.exceptions import *
from selenium.webdriver.common.keys import Keys

elevate.elevate()

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
    time.sleep(2)
    driver.find_element_by_id("id_player_name").send_keys("BingoTracker")     # input nickname
    driver.find_element_by_id("id_passphrase").send_keys(pw)                  # input password
    driver.find_element_by_id("id_is_spectator").send_keys(Keys.SPACE)        # join as spectator

    # attempt login
    driver.find_element_by_class_name("form-control").submit()                # submit login
    time.sleep(10)                                                             # firefox fails here if you don't wait a bit
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



def Main(colours, track_lines, room_url, room_pw, bg_type, bg_name):

    # -------------------------------------------------------------------------------------------------------------------- #
    # start script

    scores = []

    for colour in colours:        
        scores.append("99") #append an impossible score so that the values are updated on first connection


    #OBS input section
    if bg_type == "None": #No background
        print(">>  Note that the bingosync listener is still running")
    else:
        if bg_type == "Video":
            fmt = "mkv"
            delfmt = "png"

        if bg_type == "Image":
            fmt = "png"
            delfmt = "mkv"

        if len(bg_name) == 0:
            print(">>  Note that the bingosync listener is still running")
        else:
            delete_bg(obs_path)
            if generate_OBS_media(string.capwords(bg_name), bg_type, fmt, colours):
                print(">>  OBS layout was created.")


    if room_url == "":
        return;


    driver = initialize_driver()
    if driver == None:
        sys.exit(-1)


    if not attempt_login(driver,room_url, room_pw):
        return;


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


    delete_copies()

    print(">>  Listener terminated")
    print(">>  Press CTRL+C to exit")



class DragDropListbox(tk.Listbox):
    """ A Tkinter listbox with drag'n'drop reordering of entries. """
    def __init__(self, master, **kw):
        kw['selectmode'] = tk.SINGLE
        tk.Listbox.__init__(self, master, kw)
        self.bind('<Button-1>', self.setCurrent)
        self.bind('<B1-Motion>', self.shiftSelection)
        self.curIndex = None

    def setCurrent(self, event):
        self.curIndex = self.nearest(event.y)

    def shiftSelection(self, event):
        i = self.nearest(event.y)
        if i < self.curIndex:
            x = self.get(i)
            self.delete(i)
            self.insert(i+1, x)
            self.curIndex = i
        elif i > self.curIndex:
            x = self.get(i)
            self.delete(i)
            self.insert(i-1, x)
            self.curIndex = i


top = tk.Tk()

videoOrImage = StringVar()
videoOrImage.set("Image")

rowLineCounter = BooleanVar()

bingoImgPath = StringVar()
bingoImgPath.set("Sheo")

bingoURL = StringVar()
bingoPW = StringVar()

Label(top, text="Colours (drag to reorder p1 in 1st slot, p2 in 2nd slot etc)").grid( sticky=W,row = 0, column = 0, columnspan = 3, padx=10, pady=0)

pColours = DragDropListbox(top, selectmode=tk.BROWSE)
pColours.grid( sticky=W+E,row = 1, column = 0, columnspan = 3, padx=10, pady=0)
x = 0
for item in ["Orange", "Red", "Blue", "Green", "Purple", "Navy", "Teal", "Brown", "Pink", "Yellow"]:
    pColours.insert(x, item)
    x = x + 1
pColours


Label(top, text="").grid( sticky=W,row = 10, column = 0, columnspan = 3, padx=0, pady=0)

Label(top, text="Which background format would you like to use?").grid( sticky=W,row = 11, column = 0, columnspan = 3, padx=10, pady=0)

Radiobutton(top, text="Video", variable=videoOrImage, value="Video").grid( sticky=W,row = 12, column = 0, columnspan = 3, padx=10, pady=0)
Radiobutton(top, text="Image", variable=videoOrImage, value="Image").grid( sticky=W,row = 12, column = 1, columnspan = 3, padx=10, pady=0)
Radiobutton(top, text="None", variable=videoOrImage, value="None").grid( sticky=W,row = 12, column = 2, columnspan = 3, padx=10, pady=0)


Label(top, text="Name of background file").grid( sticky=W,row = 15, column = 0, columnspan = 3, padx=10, pady=0)
Entry(top, textvariable=bingoImgPath).grid( sticky=W+E,row = 16, column = 0, columnspan = 3, padx=10, pady=0)

Checkbutton(top, text="Check this if the row/line counter is relevant to the score", variable=rowLineCounter).grid( sticky=W,row = 20, column = 0, columnspan = 3, padx=10, pady=10)

Label(top, text="Bingosync room URL (Leave blank for no bingo)").grid( sticky=W,row = 30, column = 0, columnspan = 3, padx=10, pady=0)
Entry(top, textvariable=bingoURL).grid( sticky=W+E,row = 31, column = 0, columnspan = 3, padx=10, pady=0)

Label(top, text="Bingosync room password (Leave blank for no bingo)").grid( sticky=W,row = 32, column = 0, columnspan = 3, padx=10, pady=0)
Entry(top, textvariable=bingoPW).grid( sticky=W+E,row = 33, column = 0, columnspan = 3, padx=10, pady=0)

def callback():

    colours = []
    for ind in range(0, pColours.size()):
        colours.append(pColours.get(ind).lower())

    Main(colours, rowLineCounter.get(), bingoURL.get(), bingoPW.get(), videoOrImage.get(), bingoImgPath.get())

def finish():
    sys.exit(0)

b = Button(top, text="Start Tracker", bg="#cccccc", command=callback).grid( sticky=W+E,row = 40, column = 0, columnspan = 3, padx=10, pady=(8,0))
c = Button(top, text="Exit", bg="#cccccc", command=finish).grid( sticky=W+E,row = 41, column = 0, columnspan = 3, padx=10, pady=2)

for x in range(3):
    Grid.columnconfigure(top,x,weight=1)
for y in range(15):
    Grid.rowconfigure(top,y,weight=1)

top.title("BingoTracker")
top.mainloop()   
