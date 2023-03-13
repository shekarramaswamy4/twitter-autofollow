# tracks with https://gist.github.com/shekarramaswamy4/41bdc6ea7e9e0774b581e6d72c8e7255

# This script takes an input CSV you received from shekarramaswamy
# The CSV should be in the same directory that you're running this file from
# It will open all profiles in the CSV automatically in Chrome for your convenience

import csv
import webbrowser

# MacOS Chrome path
chrome_path = 'open -a /Applications/Google\ Chrome.app %s'

# Update this with your csv path
csv_filename = "shekarramaswamy-paigecraig-mutuals.csv"

with open(csv_filename, mode ='r') as csvfile:
    reader = csv.reader(csvfile)

    for line in reader:
        webbrowser.get(chrome_path).open(line[0])
