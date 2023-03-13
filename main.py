import os
import tweepy
import requests
import time
from datetime import datetime, timedelta
import csv

#############
# API Setup #
#############
bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")
client = tweepy.Client(bearer_token, wait_on_rate_limit=True)
# Sometimes the client doesn't support the functionality we want, so we have to roll our own queries
headers = {"Authorization": f"Bearer {bearer_token}"}

#############
# Constants #
#############
mutuals_threshold = 5
# Skip mutual checking if over 1000 followers for rate limit protection
max_followers_for_skip = 1000
min_followers = 100
max_ratio_follower_to_following = 1.1
min_ratio_follower_to_following = 0.3
min_tweet_count = 10
# User has to have been active in the last 30 days
tweet_days_cutoff = 30
# To preserve rate limits, match up to certain amt strong mutuals
good_mutuals_limit = 10

# Small optimization used when analyzing follower accounts
# Only used in memory
tweeted_recently_cache = {}

####################
# Twitter Accounts #
####################
class TwitterAccount:
    def __init__(self, username, twid, num_followers, num_following, tweet_count):
        self.username = username 
        self.twid = twid
        self.num_followers = num_followers
        self.num_following = num_following
        self.tweet_count = tweet_count

def get_twid_for_username(username):
    user = client.get_user(username=username)
    return user.data["id"]

# returns {str (twitter_username): TwitterAccount}
def get_following_for_id(twid):
    following = {}

    pagination_token = None
    while True:
        following_url = f"https://api.twitter.com/2/users/{twid}/following?user.fields=public_metrics&max_results=1000"

        if pagination_token:
            following_url += "&pagination_token=" + pagination_token
        following_res = requests.get(following_url, headers=headers).json()

        for f in following_res["data"]:
            tw_username = f["username"]
            f_twid = f["id"]
            num_followers = f["public_metrics"]["followers_count"]
            num_following = f["public_metrics"]["following_count"]
            tweet_count = f["public_metrics"]["tweet_count"]

            following[tw_username.lower()] = TwitterAccount(tw_username, f_twid, num_followers, num_following, tweet_count)
        
        if "next_token" in following_res["meta"]:
            pagination_token = following_res["meta"]["next_token"]
        else:
            break

    return following

# returns {str (twitter_username): TwitterAccount}
def get_followers_for_id(twid):
    followers = {}

    pagination_token = None
    # Perform some basic limiting on fetching followers
    # This check is only needed for the initial follower fetching of the target b/c the mutuals check for <1k happens
    # before this
    while True:
        followers_url = f"https://api.twitter.com/2/users/{twid}/followers?user.fields=public_metrics&max_results=1000"

        if pagination_token:
            followers_url += "&pagination_token=" + pagination_token
        followers_res = requests.get(followers_url, headers=headers)
        # Rate limited!!!
        if followers_res.status_code == 429:
            print(f"Rate limited, sleeping")
            time.sleep(60 * 16) # sleep over 15 min b/c thats the twitter rate limit window
            followers_res = requests.get(followers_url, headers=headers)
        followers_res = followers_res.json()

        for f in followers_res["data"]:
            tw_username = f["username"]
            f_twid = f["id"]
            num_followers = f["public_metrics"]["followers_count"]
            num_following = f["public_metrics"]["following_count"]
            tweet_count = f["public_metrics"]["tweet_count"]

            followers[tw_username.lower()] = TwitterAccount(tw_username, f_twid, num_followers, num_following, tweet_count)
        
        if "next_token" in followers_res["meta"]:
            pagination_token = followers_res["meta"]["next_token"]
        else:
            break

    return followers

# finds the intersection in keys between the two input parameters
# in reality, the two input paramters are:
# following: who the current account follows
# followers: who the target account is followed by
# mutuals are defined by current account following the same person that follows the target account
# called by compute_mutuals_for_target_followers
def count_mutuals(following, followers):
    count = 0

    # minor performance optimization to lesson number of iterations
    if len(following) < len(followers):
        for usr in following.keys():
            if usr in followers:
                count += 1
        return count
    
    for usr in followers.keys():
        if usr in following:
            count += 1
    return count

# For each target follower, check how many mutuals my_following 
# This calls count_mutuals
def compute_mutuals_for_target_followers(target_followers, my_following, my_username):
    good_mutuals = {}
    bad_mutuals = {}

    print(f"Good mutuals for {my_username}")
    for tw_username, f in target_followers.items():
        # Preserve rate limits
        if f.num_followers >= max_followers_for_skip:
            print(f"Skipping {tw_username} due to {f.num_followers} followers")
            continue 

        derivative_followers = get_followers_for_id(f.twid)
        num_mutuals = count_mutuals(my_following, derivative_followers)

        if num_mutuals >= mutuals_threshold:
            good_mutuals[tw_username] = num_mutuals
            print(f"https://twitter.com/{tw_username}, {tw_username}")
        else:
            bad_mutuals[tw_username] = num_mutuals
        
        if len(good_mutuals) >= good_mutuals_limit:
            break

    return good_mutuals, bad_mutuals

# params: followers of target account, followers of current account
# params: {str (twitter_username): TwitterAccount}, {str (twitter_username): TwitterAccount}
# 
# Filter followers by:
# 1. at least min_followers
# 2. an acceptable follower ratio
# 3. tweeted at least min_tweet_count times
def filter_followers_by_stats(followers, my_followers, my_username): 
    # There is probably a better way to filter a dictionary but it's fine for now
    filtered = {}

    for tw_username, f in followers.items():
        if tw_username == my_username:
            continue
        if tw_username in my_followers:
            continue
        elif f.num_followers < min_followers:
            continue
        elif f.num_following == 0:
            continue
        elif f.tweet_count < min_tweet_count:
            continue

        follow_ratio = f.num_followers / f.num_following
        # follow ratio should be within the two set boundaries
        if not (follow_ratio <= max_ratio_follower_to_following and follow_ratio >= min_ratio_follower_to_following):
            continue

        # Check cache to avoid rate limits where possible
        if tw_username in tweeted_recently_cache:
            if tweeted_recently_cache[tw_username]:
                filtered[tw_username] = f
            continue

        cutoff = datetime.utcnow() - timedelta(days=tweet_days_cutoff)
        # https://docs.tweepy.org/en/stable/asyncclient.html#tweepy.asynchronous.AsyncClient.get_users_tweets
        past_tweet_data = client.get_users_tweets(f.twid, max_results=5, start_time=cutoff)
        if "result_count" not in past_tweet_data.meta or past_tweet_data.meta["result_count"] == 0:
            tweeted_recently_cache[tw_username] = False
        else:
            tweeted_recently_cache[tw_username] = True
            filtered[tw_username] = f
        
    return filtered

def run(my_username, target_username, use_mutuals=False, write_csv=False):
    print("----------")
    print(f"Running for {my_username}, targeting {target_username}")
    my_user = client.get_user(username=my_username)
    my_id = my_user.data["id"]
    print(f"My User id {my_id}")
    my_followers = get_followers_for_id(my_id)
    my_following = get_following_for_id(my_id)
    print(f"{my_username} has {len(my_followers)} followers")

    target_user = client.get_user(username=target_username)
    target_id = target_user.data["id"]

    followers = get_followers_for_id(target_id)
    print(f"Found {len(followers)} for {target_username}")
    filtered_followers_stats = filter_followers_by_stats(followers, my_followers, my_username)
    print(f"Filtered by stats down to {len(filtered_followers_stats)} for {target_username}")

    if write_csv:
        with open(f"{my_username}-{target_username}-base.csv", "w") as csvfile:
            writer = csv.writer(csvfile) 
            for tw_username in filtered_followers_stats.keys():
                writer.writerow([f"https://twitter.com/{tw_username}", tw_username])

    if use_mutuals:
        good_mutuals, bad_mutuals = compute_mutuals_for_target_followers(filtered_followers_stats, my_following, my_username)
        print(f"Bad mutuals for {my_username}")
        print(bad_mutuals)
        with open(f"{my_username}-{target_username}-mutuals.csv", "w") as csvfile:
            writer = csv.writer(csvfile) 
            for tw_username, num_mutuals in good_mutuals.items():
                writer.writerow([f"https://twitter.com/{tw_username}", tw_username, num_mutuals])

"""
Get followers for a user:
{
    'data': [
        {'name': 'Ryan Robinson', 'username': 'Ryan__Robinson', 'public_metrics': {'followers_count': 8, 'following_count': 32, 'tweet_count': 2, 'listed_count': 0}, 'id': '720288541880815616'}, 
        {'name': 'Hayteng Wong', 'username': 'haywong__', 'public_metrics': {'followers_count': 0, 'following_count': 12, 'tweet_count': 0, 'listed_count': 0}, 'id': '1565859014269104128'}
    ],
    'meta': {'result_count': 2, 'next_token': 'I9HRDFPE1GO1GZZZ'}}
"""

"""Thoughts
Actually following users requires OAuth 1.0a approval from Twitter, which is easy enough to get but not worth the time right now. For now, it should be sufficient to run this program to generate a list of people to follow, and then put it into phantombuster to start the auto follow-unfollow sequence.
You may be thinking, phantombuster offers the same functionality! Well, they don't perform additional filtering on target accounts, which wastes time and energy. We want high quality followers.
TODO:
1) pickle?
"""
