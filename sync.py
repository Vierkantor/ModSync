#!/usr/bin/env python3

# sync.py: Syncs your modded minecraft version with that of the server
# Licensed under WTFPL, http://wtfpl.org

# Requirements: ATLauncher (or similar)
# Including a copy of regular Minecraft, with the right version of Minecraft Forge installed (messing with the jars is a bit too complicated)

# Example usages:
# * Start a regular ATLauncher instance ./sync.py http://example.com/file/mods.json ~/ATLauncher
# * Start your minecraft server ./sync.py http://localhost/file/mods.json . -y -c 'nohup ./server.sh &'

import argparse;
import json;
import os;
import shutil;
import sys;
import urllib;
import urllib.parse;
import urllib.request;
import zipfile;

# ask the user for confirmation
def prompt(message, options):
	print("{} [{}]".format(message, options));
	if args.alwaysyes:
		print("Assuming yes...");
		return True;
	
	answer = input(">");
	if len(answer) > 0 and (answer[0] == 'y' or answer[0] == 'Y'):
		return True;
	elif len(answer) > 0 and (answer[0] == 'n' or answer[0] == 'N'):
		return False;
	else:
		return 'Y' in options;

def download(url, filename):
	with urllib.request.urlopen(url) as response, open(filename, 'wb') as outFile:
		shutil.copyfileobj(response, outFile);

parser = argparse.ArgumentParser(description="Syncs your modded minecraft version with that of the server");
# update locations
parser.add_argument("url", help="The full URL pointing to a mods.json file");
parser.add_argument("-n", "--name", default=None, help="Alternate instance name (instead of the server's domain name with a capital letter)");
parser.add_argument("dir", nargs='?', default=os.getcwd(), help="The main ATLauncher directory (including things like Instances)");
parser.add_argument("-i", "--instancedir", default=None, help="The directory containing the instances themselves (if you don't like ATLauncher)");
parser.add_argument("-p", "--packdir", default=None, help="The directory of the instance itself (if you really don't like launchers)");

# update options
parser.add_argument("-o", "--overwrite", action="store_const", const=True, default=False, help="Overwrite all mod files (ensures they are fresh)");

# launch info
parser.add_argument("-L", "--nolaunch", action="store_const", const=True, default=False, help="Don't start Minecraft (ATLauncher) after syncing (default: do)");
parser.add_argument("-c", "--command", default=None, help="The command to run after syncing (handy to update and launch in one go)");

# other switches
parser.add_argument("-y", "--alwaysyes", action="store_const", const=True, default=False, help="Answer yes to all questions (DANGEROUS: might say yes to eating your files)");

args = parser.parse_args(sys.argv[1:]);

# check for an already installed instance
if args.name:
	packName = args.name;
else:
	# get the name from the domain name of the mods.json
	#													without the tld 
	#																   and capitalized
	packName = urllib.parse.urlparse(args.url).hostname.split('.')[-2].capitalize();

# find paths to the base instances
if args.packdir:
	packDir = args.packdir;
else:
	if args.instancedir:
		instanceDir = args.instancedir;
	else:
		instanceDir = os.path.join(args.dir, "Instances");
	
	packDir = os.path.join(instanceDir, packName);

if os.path.isdir(packDir):
	print("Found (presumably) installed instance at {}".format(packDir));
else:
	# check if we actually have any instances
	vanillaDir = os.path.join(instanceDir, "VanillaMinecraft");
	if not os.path.isdir(vanillaDir):
		print("Could not find a basic Minecraft instance here ({}).".format(instanceDir));
		print("Make sure you have one installed and add in the right Minecraft Forge version too.");
		sys.exit(1);

	print("Found vanilla minecraft installation at {}.".format(vanillaDir));
	
	print("No installed instance found at {}.".format(packDir));
	if not prompt("Create new one?", "Yn"):
		print("Could not find a modded Minecraft instance.");
		sys.exit(1);
	
	# copy the vanilla instance
	shutil.copytree(vanillaDir, packDir);
	
	# and modify its instance.json
	with open(os.path.join(packDir, "instance.json"), "r") as instanceFile:
		instanceData = json.load(instanceFile);
	
	instanceData["name"] = packName;
	instanceData["pack"] = packName;
	
	with open(os.path.join(packDir, "instance.json"), "w") as instanceFile:
		json.dump(instanceData, instanceFile);

# reload instance data
with open(os.path.join(packDir, "instance.json"), "r") as instanceFile:
	instanceData = json.load(instanceFile);

# now we have a (working, hopefully) minecraft instance. Let's check for updates!

# get the server's mods.json
serverModsFile = urllib.request.urlopen(args.url);
serverModsData = json.loads(str(serverModsFile.read(), encoding="utf-8"));
if serverModsData["version"] not in [1]:
	print("Server has incompatible mod data version: {}, expected [1]".format(serverModsData["version"]));
	sys.exit(2);
if serverModsData["minecraft"] != instanceData["minecraftVersion"]:
	print("Server has incompatible minecraft version: {}, you have {}".format(serverModsData["minecraft"], instanceData["minecraftVersion"]));
	sys.exit(2);

# update configuration files
if prompt("Update and possibly overwrite config files?", "Yn"):
	download(serverModsData["config"], "config.zip");
	
	# unzip it, adding new files and replacing old ones (keeping custom files)
	shutil.unpack_archive("config.zip", packDir);
	
	print("Config files updated.");

# update mod files
if prompt("Update and definitely overwrite mod files?", "Yn"):
	# make a backup because problems downloading may eat the files
	# but remove the old backup first
	if os.path.isdir(os.path.join(packDir, "mods_unsynced")):
		shutil.rmtree(os.path.join(packDir, "mods_unsynced"));
	
	if args.overwrite:
		shutil.move(os.path.join(packDir, "mods"), os.path.join(packDir, "mods_unsynced"));	
		os.makedirs(os.path.join(packDir, "mods"));
	else:
		shutil.copytree(os.path.join(packDir, "mods"), os.path.join(packDir, "mods_unsynced"));
	print("Mods have been backed up at mods_unsynced/");
	
	# if something goes wrong, make sure to keep everything working
	try:
		# find all the newly required files
		serverFilenames = [];
		for mod in serverModsData["mods"]:
			filename = mod["version"]["filename"];
			serverFilenames.append(filename);
			
			# download them if they're missing
			if not os.path.isfile(os.path.join(packDir, "mods", filename)):
				if mod["version"]["method"] == "ignore":
					# somehow, non-mod files end up in the mods directory. This is obviously bad, but let's ignore them
					pass;
				elif mod["version"]["method"] == "wget":
					# download it regularly
					print("Downloading {}".format(filename));
					try:
						download(mod["version"]["url"], os.path.join(packDir, "mods", filename));
					except urllib.error.HTTPError as err:
						print("Error downloading {}.".format(mod["version"]["url"]));
						if prompt("Continue anyway?", "yN"):
							# don't launch a broken instance
							print("Warning: you need to manually download this file to launch.");
							args.nolaunch = True;
						else:
							raise err;
				else:
					# some mods are prohibited from automatic downloading
					print("Manual download required for {}!".format(mod["name"]));
					print("Required filename: {}".format(mod["version"]["filename"]));
					if "url" in mod["version"]:
						print("Find it at {}".format(mod["version"]["url"]));
					else:
						print("Find it at {}".format(mod["website"]));
					# don't launch a half-installed instance
					args.nolaunch = True;
		
		# remove all the outdated files
		for item in os.listdir(os.path.join(packDir, "mods")):
			if os.path.isfile(os.path.join(packDir, "mods", item)) and item not in serverFilenames:
				os.remove(os.path.join(packDir, "mods", item));
	except:
		# move the backup back in place
		shutil.rmtree(os.path.join(packDir, "mods"));
		shutil.move(os.path.join(packDir, "mods_unsynced"), os.path.join(packDir, "mods"));
		print("Backup replaced.");
		
		raise;
	
	print("Mod files updated.");

print("Synced your version to the server. Enjoy.");

# start ATLauncher if asked
if not args.nolaunch:
	if args.command:
		os.system(args.command);
	else:
		os.system("java -jar {}".format(os.path.join(args.dir, "ATLauncher.jar")));
