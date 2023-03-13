# twitter-autofollow

Twitter-autofollow is a script that finds high quality twitter accounts that are likely to follow you back based on a number of heuristics.

## How to use
1. Sign up for a Twitter developer account (developer.twitter.com)
2. Get a TWITTER_BEARER_TOKEN

<img width="1101" alt="Screen Shot 2023-03-13 at 12 59 00 PM" src="https://user-images.githubusercontent.com/31163793/224818472-95a097c8-843f-4d38-8313-532019d77246.png">

3. Add that to an env var where you're going to run the script
4. Add a call to `run` in the python script: `run("YOUR_USERNAME", "TARGET_USERNAME", use_mutuals=True, write_csv=True)`
5. The output will be two csvs. The higher quality followers are in the `mutuals` spreadsheet.

