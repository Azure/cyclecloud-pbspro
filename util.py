from configparser import ConfigParser
import os
from subprocess import run

RELEASE_URL = (
        "https://github.com/Azure/cyclecloud-pbspro/releases/download/2023-03-29-bins"
        )
RELEASE_URL = RELEASE_URL.rstrip("/") + "/"

def download_release_files():
    blobs = get_blobs()
    for _, fname in enumerate(blobs):
        if fname == "cyclecloud_api":
                continue
    
        url = os.path.join(RELEASE_URL, fname)
        run(["curl", "-L", "-C", "-", "-s", "-O", url], cwd="blobs", check=True)

def get_blobs():     
     parser = ConfigParser()
     parser.read("project.ini")
     blobs = [x.strip() for x in parser.get("blobs", "Files").split(",") if "cyclecloud-pbspro-pkg" not in x]

     return blobs

