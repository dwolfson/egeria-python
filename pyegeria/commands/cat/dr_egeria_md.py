"""
This is an ongoing experiment in parsing and playing with Freddie docs
"""
import argparse
import json
import os
from rich import print
from rich.console import Console
from rich.prompt import Prompt


import click
from pyegeria import (extract_command, process_glossary_upsert_command, process_term_upsert_command,
                      process_categories_upsert_command, process_provenance_command,
                      get_current_datetime_string, process_per_proj_upsert_command, command_list,EgeriaTech,
                      )
from datetime import datetime

EGERIA_METADATA_STORE = os.environ.get("EGERIA_METADATA_STORE", "active-metadata-store")
EGERIA_KAFKA_ENDPOINT = os.environ.get("KAFKA_ENDPOINT", "localhost:9092")
EGERIA_PLATFORM_URL = os.environ.get("EGERIA_PLATFORM_URL", "https://localhost:9443")
EGERIA_VIEW_SERVER = os.environ.get("EGERIA_VIEW_SERVER", "view-server")
EGERIA_VIEW_SERVER_URL = os.environ.get(
    "EGERIA_VIEW_SERVER_URL", "https://localhost:9443"
)
EGERIA_INTEGRATION_DAEMON = os.environ.get("EGERIA_INTEGRATION_DAEMON", "integration-daemon")
EGERIA_INTEGRATION_DAEMON_URL = os.environ.get(
    "EGERIA_INTEGRATION_DAEMON_URL", "https://localhost:9443"
)
EGERIA_ADMIN_USER = os.environ.get("ADMIN_USER", "garygeeke")
EGERIA_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "secret")
EGERIA_USER = os.environ.get("EGERIA_USER", "erinoverview")
EGERIA_USER_PASSWORD = os.environ.get("EGERIA_USER_PASSWORD", "secret")
EGERIA_WIDTH = os.environ.get("EGERIA_WIDTH", 220)
EGERIA_JUPYTER = os.environ.get("EGERIA_JUPYTER", False)
EGERIA_HOME_GLOSSARY_GUID = os.environ.get("EGERIA_HOME_GLOSSARY_GUID", None)
EGERIA_GLOSSARY_PATH = os.environ.get("EGERIA_GLOSSARY_PATH", None)
EGERIA_ROOT_PATH = os.environ.get("EGERIA_ROOT_PATH", "/Users/dwolfson/localGit/egeria-v5-3/egeria-python")
EGERIA_INBOX_PATH = os.environ.get("EGERIA_INBOX_PATH", "pyegeria/commands/cat/dr_egeria_inbox")
EGERIA_OUTBOX_PATH = os.environ.get("EGERIA_OUTBOX_PATH", "pyegeria/commands/cat/dr_egeria_outbox")





@click.command("process_markdown_file", help="Process a markdown file and return the output as a string.")
@click.option("--file-path", help="File path to markdown file",
              default="glossary_exp.md", required=True, prompt=False)
@click.option("--directive", default="display", help="How to process the file",
              type=click.Choice(["display","validate","process"],case_sensitive=False), prompt=False,)
@click.option("--server", default=EGERIA_VIEW_SERVER, help="Egeria view server to use.")
@click.option(
    "--url", default=EGERIA_VIEW_SERVER_URL, help="URL of Egeria platform to connect to"
)
@click.option("--userid", default=EGERIA_USER, help="Egeria user")
@click.option("--user_pass", default=EGERIA_USER_PASSWORD, help="Egeria user password")
def process_markdown_file(
        file_path: str,
        directive: str,
        server: str,
        url: str,
        userid: str,
        user_pass: str,
        )-> None:
    """
    Process a markdown file by parsing and executing Dr. Egeria commands. Write output to a new file.
    """

    console = Console(width=int(EGERIA_WIDTH))
    client = EgeriaTech(server, url, user_id=userid)
    token = client.create_egeria_bearer_token(userid, user_pass)

    updated = False
    full_file_path = os.path.join(EGERIA_ROOT_PATH, EGERIA_INBOX_PATH, file_path)
    print(f"Processing Markdown File: {full_file_path}")
    try:
        with open(full_file_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File not found at path: {full_file_path}")
        return {}  # Return empty dict if file not found

    final_output = []
    prov_found = False
    prov_output = (f"\n# Provenance\n\n* Results from processing file {file_path} on "
                    f"{datetime.now().strftime("%Y-%m-%d %H:%M")}\n")
    h1_blocks = []
    current_block = ""
    in_h1_block = False
    element_dictionary = {}

    # Helper function to process the current block
    def process_current_block(current_block):
        nonlocal updated, final_output, prov_found, prov_output, h1_blocks, in_h1_block, element_dictionary

        if not current_block:
            return  # No block to process

        potential_command = extract_command(current_block)  # Extract command
        if potential_command in command_list:
            # Process the block based on the command
            if potential_command == "Provenance":
                result = process_provenance_command(file_path, current_block)
                prov_found = True

            elif potential_command in ["Create Glossary", "Update Glossary"]:
                result = process_glossary_upsert_command(client, element_dictionary, current_block, directive)
            elif potential_command in ["Create Category", "Update Category"]:
                result = process_categories_upsert_command(client, element_dictionary, current_block, directive)
            elif potential_command in ["Create Term", "Update Term"]:
                result = process_term_upsert_command(client, element_dictionary, current_block, directive)
            elif potential_command in ["Create Personal Project", "Update Personal Project"]:
                result = process_per_proj_upsert_command(client, element_dictionary, current_block, directive)
            else:
                # If command is not recognized, keep the block as-is
                result = None

            if result:
                if directive == "process":
                    updated = True
                    final_output.append(result)
                    # print(json.dumps(element_dictionary, indent=4))
                # elif directive == "validate":
                #     print(json.dumps(element_dictionary, indent=4))
            elif directive == "process":
                # Handle errors (skip this block but notify the user)
                print(f"\n==>\tErrors found while processing command: \'{potential_command}\'\n"
                      f"\tPlease correct and try again. \n")
                final_output.append(current_block)
        else:
            # If there is no command, append the block as-is
            final_output.append(current_block)

    # Main parsing loop
    for line in lines:
        line = line.strip()  # Remove leading/trailing whitespace

        # Handle a new H1 block (starting with `# `)
        if line.startswith("# "):
            if in_h1_block:
                # Process the current block before starting a new one
                process_current_block(current_block)

            # Start a new H1 block
            current_block = line
            in_h1_block = True

        # Handle the end of a block (line starts with `---`)
        elif line.startswith("---"):
            if in_h1_block:
                # Process the current block when it ends with `---`
                current_block += f"\n{line}"
                process_current_block(current_block)
                current_block = ""  # Clear the block
                in_h1_block = False

        # Add lines to the current H1 block
        elif in_h1_block:
            current_block += f"\n{line}"

        # Append non-H1 content directly to the output
        else:
            final_output.append(line)

    # Ensure the final H1 block is processed if the file doesn't end with `---`
    if in_h1_block:
        process_current_block(current_block)

    # Join the final output list into a single string
    final_output = "\n".join(final_output)


    try:
        if updated:
            path, filename = os.path.split(file_path)  # Get both parts
            new_filename = f"processed-{get_current_datetime_string()}-{filename}"  # Create the new filename
            new_file_path = os.path.join(EGERIA_ROOT_PATH, EGERIA_OUTBOX_PATH, new_filename)  # Construct the new path
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)

            with open(new_file_path, 'w') as f2:
                f2.write(final_output)
                if not prov_found:
                    f2.write(prov_output)
            click.echo(f"\n==> Notebook written to {new_file_path}")
        else:
            click.echo("\nNo updates detected. New File not created.")

    except (Exception):
        console.print_exception(show_locals=True)


# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--server", help="Name of the server to display status for")
#     parser.add_argument("--url", help="URL Platform to connect to")
#     parser.add_argument("--userid", help="User Id")
#     parser.add_argument("--password", help="User Password")
#     parser.add_argument("--time_out", help="Time Out")
#
#     args = parser.parse_args()
#
#     server = args.server if args.server is not None else EGERIA_VIEW_SERVER
#     url = args.url if args.url is not None else EGERIA_PLATFORM_URL
#     userid = args.userid if args.userid is not None else EGERIA_USER
#     user_pass = args.password if args.password is not None else EGERIA_USER_PASSWORD
#     time_out = args.time_out if args.time_out is not None else 60
#     try:
#         file_path = Prompt.ask("Markdown File name to process:", default="")
#         directive = Prompt.ask("Processing Directive:", choices=[ "display", "validate", "process"], default="validate")
#
#         process_markdown_file(file_path, directive, server, url, userid, user_pass)
#     except KeyboardInterrupt:
#         pass
#
#
# if __name__ == "__main__":
#     main()
