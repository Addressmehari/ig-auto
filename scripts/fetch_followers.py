import argparse
import sys
import os
from instagrapi import Client

def main():
    parser = argparse.ArgumentParser(description="Fetch Instagram followers and save them to a file.")
    parser.add_argument("target", help="The target Instagram username to fetch followers from")
    parser.add_argument("-s", "--session-file", help="Path to the saved session file (default: session.json)", default="session.json")
    parser.add_argument("-o", "--output", help="Output file path (default: followers.txt)", default="followers.txt")
    parser.add_argument("-n", "--amount", type=int, help="Number of followers to fetch (default: all). Note: Fetching all can take a long time for large accounts.", default=0)
    parser.add_argument("--delay", type=int, nargs=2, metavar=('MIN', 'MAX'), help="Random delay in seconds between API requests (e.g., --delay 5 15). Recommended to prevent bans.", default=[2, 5])
    args = parser.parse_args()

    if not os.path.exists(args.session_file):
        print(f"Error: Session file '{args.session_file}' not found.")
        print("Please run 'python scripts/create_session.py <your_username>' first to generate a session.")
        sys.exit(1)

    cl = Client()
    # Set random delays between API requests to mimic human behavior and avoid bans
    cl.delay_range = args.delay
    
    print(f"Loading session from {args.session_file}...")
    try:
        cl.load_settings(args.session_file)
        # Note: We rely on the saved session being valid. If it's expired, the API calls below will fail.
    except Exception as e:
        print(f"Failed to load session: {e}")
        sys.exit(1)

    print(f"Getting user ID for target: {args.target}...")
    try:
        user_id = cl.user_id_from_username(args.target)
    except Exception as e:
        print(f"Failed to get user ID for {args.target}. Ensure your session is valid or the target exists. Error: {e}")
        sys.exit(1)
        
    print(f"Fetching followers for {args.target} (ID: {user_id})...")
    try:
        # user_followers returns a dict of {user_id: UserShort}
        if args.amount > 0:
            followers = cl.user_followers(user_id, amount=args.amount)
        else:
            # 0 means fetch all followers
            followers = cl.user_followers(user_id)
            
        print(f"Successfully fetched {len(followers)} followers.")
        
        print(f"Writing to {args.output}...")
        with open(args.output, "w", encoding="utf-8") as f:
            usernames = [user_info.username for user_info in followers.values()]
            f.write(",".join(usernames))
                
        print(f"Done! Followers saved to {args.output}")
        
    except Exception as e:
        print(f"Failed to fetch followers: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

