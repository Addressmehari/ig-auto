import argparse
import sys
import getpass
from instagrapi import Client

def main():
    parser = argparse.ArgumentParser(description="Create and save an Instagram session file to prevent repeated logins.")
    parser.add_argument("username", help="Your Instagram username")
    parser.add_argument("-s", "--session-file", help="Path to save the session file (default: session.json)", default="session.json")
    args = parser.parse_args()

    password = getpass.getpass(f"Enter Instagram password for {args.username}: ")

    cl = Client()
    
    print(f"Logging in as {args.username}...")
    try:
        cl.login(args.username, password)
        print("Login successful!")
        
        print(f"Saving session to {args.session_file}...")
        cl.dump_settings(args.session_file)
        print("Session saved successfully!")
        print(f"You can now use '{args.session_file}' in other scripts without providing your password again.")
    except Exception as e:
        print(f"Login or session save failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
