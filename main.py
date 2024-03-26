import mwclient.errors
from mwclient import Site
import os
from pathlib import Path
import pandas as pd
from dotenv import dotenv_values
import time
import numpy as np
import re
import argparse
import json


config = {
    **dotenv_values(".env.remote"),
    **dotenv_values(".env.local"),
    **os.environ,
}

ACCEPTED_VALUES = {"true", "t", "yes", "y", "1"}

config["WIKI_URL"] = f"{config['WIKI_URL']}:{config['PORT']}" if config["PORT"] else config["WIKI_URL"]
WIKI_URL_FULL = f"{config['WIKI_URL']}{config['WIKI_PATH']}index.php"
config["FORCE_LOGIN"] = config["FORCE_LOGIN"] and config["FORCE_LOGIN"].lower() in ACCEPTED_VALUES
config["SPREADSHEET_PATH"] = (Path.cwd() / config["SPREADSHEET_PATH"]).resolve()
config["SEED_DIR"] = (Path.cwd() / config["SEED_DIR"]).resolve()
config["EFFECT_NAME_MAP_FILE"] = (Path.cwd() / config["EFFECT_NAME_MAP_FILE"]).resolve()
config["ALLOWED_SEED_PARENT_DIRS"] = config["ALLOWED_SEED_PARENT_DIRS"].split(",")
config["MAPOBJECT_INFOBOX_PARAMS"] = config["MAPOBJECT_INFOBOX_PARAMS"].split(",")
config["MAPOBJECT_TEXTBOX_PARAMS"] = config["MAPOBJECT_TEXTBOX_PARAMS"].split(",")
config["MACRO_ENTITIES"] = config["MACRO_ENTITIES"].split(",")
HTTP_AUTH = (config["HTTP_AUTH_USERNAME"], config["HTTP_AUTH_PASSWORD"]) if config["HTTP_AUTH_USERNAME"] and config["HTTP_AUTH_PASSWORD"] else None

API_RETRY_AMOUNT = 3
API_RATE_LIMITED_WAIT_SECS = 65
FILE_UPLOAD_LIMIT = 45

parser = argparse.ArgumentParser(description="Process Wiki Data")

subparsers = parser.add_subparsers(dest="command")

seed_parser = subparsers.add_parser("seed")
upload_parser = subparsers.add_parser("upload-spreadsheet")
update_parser = subparsers.add_parser("update-wiki")

args = parser.parse_args()

with open(config["EFFECT_NAME_MAP_FILE"], "r") as f:
    data = f.read()
EFFECT_NAME_MAP = json.loads(data)

class WikiTools(Site):

    def __init__(self, url, clients_useragent, scheme, path, force_login, username, password, httpauth=None):
        super().__init__(url, clients_useragent=clients_useragent, scheme=scheme, path=path, force_login=force_login, httpauth=httpauth)
        self.api_request_counter = 0
        if username and password:
            super().login(username, password)

    def upsert_file(self, file, filename, description):
        res = super().upload(file, filename, description)

        exit_warnings = {"nochange", "duplicateversions", "duplicate", "duplicatearchive", "badfilename"}
        res_warnings = res.get("warnings")

        if not res_warnings:
            return

        # This prevents unwanted uploads; basically, only upload if there has been a change to the file.
        if len(exit_warnings & set(res["warnings"].keys())) < 1:
            super().upload(file, filename, description, ignore=True)

    def has_allowed_parent_dir(self, file_path):
        for parent in file_path.parents:
            if parent.name in config["ALLOWED_SEED_PARENT_DIRS"]:
                return True

        return False

    def upload_dir_contents(self, path, seeding=False):
        for file in path.rglob("*"):  # rglob for recursive search
            if file.is_file():
                if seeding and self.has_allowed_parent_dir(file) or not seeding:
                    print(f"Upload {file} ...")
                    try:
                        self.upsert_file(file, file.name, "")
                    except mwclient.errors.APIError as e:
                        print(f"An error occurred uploading {file} : {e}")
                    self.api_request_counter += 1
                    if self.api_request_counter % FILE_UPLOAD_LIMIT == 0:
                        print(f"Sleeping for {API_RATE_LIMITED_WAIT_SECS} seconds to stop hitting rate limit...")
                        time.sleep(API_RATE_LIMITED_WAIT_SECS)
                        self.api_request_counter = 0


    def format_mapobject_infobox(self, row, shared_df):
        infobox = "{{Infobox mapobject\n"

        card_art = str(row.get("Card Art", "nan"))
        if card_art and card_art == "nan":
            card_art = str(row.get("Icon Art", "nan"))
        if card_art and card_art != "nan":
            infobox += f"| card-image = {card_art.split('\\')[-1]}\n"

        map_art = str(row.get("Map Art", "nan"))
        if map_art and map_art != "nan":
            infobox += f"| map-image = {map_art.split('\\')[-1]}\n"

        for key, value in row.items():
            key = key.lower()
            value = str(value)
            if key in config["MAPOBJECT_INFOBOX_PARAMS"] and value and not (value == "Nan" or value == "None"):
                if key == "effect":
                    effect_type_lst = []
                    for e in value.split(" | "):
                        effect_tuple = self.format_effect(e, shared_df)
                        if effect_tuple:
                            effect_type_lst.append(f"({effect_tuple[0]}) {effect_tuple[1]}")
                    effect_str = ", ".join(effect_type_lst)
                    if effect_str:
                        infobox += f"| {key} = {effect_str}\n"

                elif key == "traits":
                    infobox += f"| {key} = {", ".join([f'[[{trait.title()}]]' for trait in value.split(", ")])}\n"
                else:
                    infobox += f"| {key} = {value}\n"

        infobox += "}}"
        return infobox

    def parse_macros(self, text, key_maps):
        def replace_func(match):
            inner_text = match.group(1).lower()
            if inner_text == "token_card":
                inner_text = "token"
            if len(inner_text.split("_")) > 1 and inner_text.split("_")[0] in config["MACRO_ENTITIES"]:
                search = "_".join(inner_text.split("_")[1:])
                val = key_maps.loc[key_maps["IDShort"] == search, "Name"].iloc[0].strip()
                return f"[[{val.title()}]]"
            elif inner_text.startswith("adv_"):
                search_str = inner_text[4:]
                for e in config["MACRO_ENTITIES"]:
                    if f"{e}_" in inner_text:
                        search_str = inner_text.split(f"{e}_")[-1]
                        break
                val = key_maps.loc[key_maps["IDShort"] == search_str, "Name"].iloc[0].strip()
                return f"[[{val.title()}]]"
            elif "^" in inner_text:
                split = inner_text.split("^")
                return f"{split[1]} {split[0]}"
            elif (key_maps['IDShort'] == inner_text).any():
                val = key_maps.loc[key_maps["IDShort"] == inner_text, "Name"].iloc[0].strip()
                return f"[[{val.title()}]]"
            elif "_" in inner_text:
                return " ".join(inner_text.split("_"))
            return inner_text

        return re.sub(r"@([^@]*)@", replace_func, text)

    def get_formatted_effect_type(self, effect_type):
        # Regex from: https://stackoverflow.com/a/9283563
        return EFFECT_NAME_MAP.get(effect_type,
                            re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1',
                                   effect_type).title())

    def format_effect(self, effect, shared_df):
        effect_type = "<No Type>"
        effect_name = "<No Name>"
        effect_description = ""

        if len(effect) > 0:
            effect = effect.strip()
            if effect.startswith("(") and effect.endswith(")"):
                return
            effect_params = effect.split(" : ")

            type_i = None
            name_i = None
            description_i = 0

            if len(effect_params) == 2:
                name_i = 0
                description_i = 1

            elif len(effect_params) == 3:
                type_i = 0
                name_i = 1
                description_i = 2

            if type_i is not None:
                effect_type = self.get_formatted_effect_type(effect_params[type_i])
            if name_i is not None:
                effect_name = effect_params[name_i] if effect_params[name_i] else "<No Name>"

            effect_description = self.parse_macros(effect_params[description_i], shared_df) if effect_params[
                description_i] else "<No Description>"
            effect_description = effect_description[0].upper() + effect_description[1:]

        return effect_type, effect_name, effect_description

    def format_mapobject_textbox(self, row, shared_df):

        ret_str = ""
        base_stats = ""
        for stat in config["MAPOBJECT_TEXTBOX_PARAMS"]:
            base_stats += "" if stat not in row or row[stat] == "None" or row[stat] == "nan" else f"* '''{stat}:''' {row[stat]}\n"

        ret_str += "" if not base_stats else f"== Base Stats ==\n\n{base_stats}\n"

        if "Effect" in row and row["Effect"] and (row["Effect"] != "None" or row["Effect"] == "nan"):
            effect_str = ""

            for e in row["Effect"].split(" | "):
                effect_tuple = self.format_effect(e, shared_df)
                if effect_tuple:
                    effect_str += f"=== {effect_tuple[0]} ===\n\n==== {effect_tuple[1]} ====\n\n{effect_tuple[2]}\n\n"

            ret_str += "" if not effect_str else f"== Effect ==\n\n{effect_str}"

        if "Traits" in row and row["Traits"] and (row["Traits"] != "None" or row["Traits"] == "nan"):
            traits_str = ""
            for trait in row["Traits"].split(", "):
                val = shared_df.loc[shared_df["IDShort"] == trait, "Name"].iloc[0].strip()
                traits_str += f"* [[{val}]]\n"
            ret_str += "" if not traits_str else f"== Traits ==\n\n{traits_str}"

        return ret_str


    def get_short_id(self, df, key):
        key = key.lower()
        if key.endswith("s"):
            key = key[:-1]
        if key == "sovereign":
            key = "citizen"
        if key == "policie":
            key = "policy"
        df["IDShort"] = df["ID"].str.split(f"{key}_").apply(lambda x: x[-1])
        return df

    def upsert_page(self, page_name, page_content, page_summary=""):
        page = self.pages[page_name]
        action = "Updating" if page.exists else "Adding"
        print(f"{action} {page_name} page `{WIKI_URL_FULL}/{page_name}` ...")
        page.edit(page_content, page_summary)

    def upload_card_data_spreadsheet(self, spreadsheet_file, engine="openpyxl"):
        dfs = pd.read_excel(spreadsheet_file, engine=engine, sheet_name=None)

        dfs = {key: df.replace(np.nan, None) for key, df in dfs.items()}

        processed_dfs = {key: self.get_short_id(value.copy(), key) for key, value in dfs.items()}
        combined_df = pd.concat(processed_dfs.values(), ignore_index=True)
        keep_columns = ["ID", "Name", "IDShort"]
        dfs["Shared"] = combined_df[keep_columns]

        for sheet_name, df in dfs.items():
            if sheet_name == "Shared":
                continue

            for _, row in df.iterrows():
                infobox = self.format_mapobject_infobox(row, dfs["Shared"])
                textbox = self.format_mapobject_textbox(row, dfs["Shared"])

                self.upsert_page(row["Name"], f"{infobox}\n\n{textbox}")
                self.api_request_counter += 1
                if self.api_request_counter % FILE_UPLOAD_LIMIT == 0:
                    print(f"Sleeping for {API_RATE_LIMITED_WAIT_SECS} to stop hitting rate limit...")
                    time.sleep(API_RATE_LIMITED_WAIT_SECS)
                    self.api_request_counter = 0

    def seed_wiki(self, seed_dir):
        for seed_subdir in [item.name for item in seed_dir.iterdir() if item.is_dir()]:
            if seed_subdir == "assets" or seed_subdir == "files":
                self.upload_dir_contents((seed_dir / seed_subdir).resolve(), seeding=True)
            else:
                for file in (seed_dir / seed_subdir).resolve().rglob("*"):
                    if file.is_file():
                        file_name = file.name
                        if file_name.split(".")[-1] in {"wikitext"}:
                            file_name = file_name.split(".")[0]
                        page_name = f"{file.parent.name}:{file_name}"
                        with file.open("r") as f:
                            file_contents = f.read()
                            self.upsert_page(page_name, file_contents)

def main():
    wt = WikiTools(config["WIKI_URL"], config["USER_AGENT"], config["SCHEME"], config["WIKI_PATH"], config["FORCE_LOGIN"], config["WIKI_USERNAME"], config["WIKI_PASSWORD"], httpauth=HTTP_AUTH)
    if args.command == "seed":
        wt.seed_wiki(config["SEED_DIR"])
    elif args.command == "upload-spreadsheet":
        wt.upload_card_data_spreadsheet(config["SPREADSHEET_PATH"])
    elif args.command == "update-wiki":
        wt.seed_wiki(config["SEED_DIR"])
        wt.upload_card_data_spreadsheet(config["SPREADSHEET_PATH"])


if __name__ == '__main__':
    main()
