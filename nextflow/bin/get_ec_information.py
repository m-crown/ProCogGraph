#!/usr/bin/env python
import pandas as pd
import json
import requests
import os
import ast
import argparse
from Bio.KEGG import Enzyme
import io
import time
import pickle
import re
from rich.progress import Progress
from rdkit import Chem
from collections import Counter
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFMCS
import pubchempy as pcp
from Bio.ExPASy import Enzyme as EEnzyme
import argparse
from pathlib import Path
from rdkit.ML.Descriptors.MoleculeDescriptors import MolecularDescriptorCalculator
from utils import get_terminal_record, get_csdb_from_glycoct, get_smiles_from_csdb, process_ec_records
from bs4 import BeautifulSoup
from urllib.parse import quote

def get_kegg_enzymes(ec_list, enzyme_string_file = None):
    def extract_reaction(ec):
        all_reacts = []
        start_appending = False
        for line in ec:
            react_list = []
            if line.startswith("ALL_REAC"):
                start_appending = True
                react_list = re.sub(r'\(.*?\)', '', line.lstrip("ALL_REAC").rstrip(";").replace(">", "").strip()).split()
            elif line.startswith("    "):
                if start_appending:
                    react_list = re.sub(r'\(.*?\)', '', line.rstrip(";").strip().replace(">", "")).split()
            else:
                start_appending = False
            react_list = [item for item in react_list if item.startswith("(") == False]
            all_reacts.extend(react_list)
        if len(all_reacts) > 0:
            return all_reacts
        else:
            return np.nan
        
    def extract_compound_codes(text):
        pattern = r'\[CPD:([^\]]+)\]'
        matches = re.findall(pattern, text)
        if len(matches) > 0: 
            return matches
        else:
            return np.nan    
    if not enzyme_string_file:
        response = requests.get(f'https://rest.kegg.jp/get/{"+".join(ec_list)}')
        if response.status_code == 200:
            response_string = response.text
        else:
            response_string = ""
            for ec in ec_list:
                enzyme_dict[ec] = {"entry" : ec, "error" : f"KEGG API returned status code {response.status_code}"}
            return enzyme_dict, response_string
    else:
        with open(enzyme_string_file, "r") as file:
            response_string = file.read()

    #biopython only extracts iubmb reactions, so here we process the records manually to get all kegg reactions
    ecs = response_string.strip("\n").split("\n///\n")
    ecs_split = [response.split("\n") for response in ecs]
    reactions = [extract_reaction(ec) for ec in ecs_split]

    enzyme_dict = {}

    enzyme_list = list(Enzyme.parse(io.StringIO(response_string)))
    enzyme_dict = {item.entry : {"entry": item.entry, 
                                    "error" : np.nan, 
                                    "matched_name" : item.name[0], 
                                    "reaction_text" : item.reaction, 
                                    "EC_substrate_codes" : extract_compound_codes(','.join(item.substrate)) if isinstance(item.substrate, list) else [],
                                    "EC_product_codes" : extract_compound_codes(','.join(item.product)) if isinstance(item.product, list) else [],
                                    "EC_dbxrefs": item.dblinks, 
                                    "EC_reactions" : reactions[idx]} for idx, item in enumerate(enzyme_list)}
                
    if set(enzyme_dict.keys()) != set(ec_list):
        missing_ecs = list(set(ec_list) - set(enzyme_dict.keys()))
        for missing_ec in missing_ecs:
            enzyme_dict[missing_ec] = {"entry" : missing_ec, "error" : "KEGG API did not return result"}
    
    return enzyme_dict, response_string

def extract_secondary_id(identifier, database_list, current_db = ""):
    #takes the identifier, and the database list
    #if the identifier is a glycan , preference is to search for the structure in the glycosmos dataset.
    #else, preference is [CHEBI,
    
    pattern = r'^G'
    match = re.match(pattern, identifier)
    
    database = None
    identifier = None
    for item in database_list:
        if database not in ["GlyTouCan", "ChEBI"]:
            if match and item[0] == "GlyTouCan" and item[0] != current_db:
                database = item[0]
                identifier = item[1][0]
            else:
                if not match and item[0] == "ChEBI" and item[0] != current_db:
                    database = item[0]
                    identifier = item[1][0]
                elif not match and item[0] == "PubChem":
                    database = item[0]
                    identifier = item[1][0]
    
    return database, identifier

def get_kegg_reactions(chunk, reactions_string_file = None):
    kegg_reaction_dictionary = {}
    if not reactions_string_file:
        response = requests.get(f'https://rest.kegg.jp/get/{ "+".join(chunk)}')
        if response.status_code == 200:
            responses_string = response.text
            response_status = 200
        else:
            for reaction in chunk:
                kegg_reaction_dictionary[reaction] = {"reaction_id": reaction, "reaction_definition" : f"KEGG Reaction not found (Error: {response.status_code}"}
            responses_string = ""
            return kegg_reaction_dictionary, responses_string
    else:
        with open(reactions_string_file, "r") as file:
            responses_string = file.read()
            response_status = "Missing from file"
        
    responses_string_split = responses_string.split("///")
    for item in responses_string_split:
        record = item.split("\n")
        for line in record:
            if line.startswith('ENTRY'):
                entry = line.split()[1]
            elif line.startswith('DEFINITION'):
                definition = line.split(maxsplit = 1)[1:]
            elif line.startswith('EQUATION'):
                equation = line.split(maxsplit = 1)[1:][0]
            elif line.startswith('ENZYME'):
                enzyme = line.split(maxsplit = 1)[1:]
        substrates, products = equation.split(' <=> ')
        substrate_codes = re.findall(r'\b[C|G]\d+\b', substrates)
        product_codes = re.findall(r'\b[C|G]\d+\b', products)
        kegg_reaction_dictionary[entry] = {"reaction_id": entry, 
                                            "reaction_definition" : definition, 
                                            "reaction_equation": equation, 
                                            "reaction_substrates": substrates, 
                                            "reaction_products" : products, 
                                            "reaction_substrate_codes" : substrate_codes, 
                                            "reaction_product_codes" : product_codes}
        for reaction in chunk:
            if reaction not in kegg_reaction_dictionary.keys():
                kegg_reaction_dictionary[reaction] = {"reaction_id": reaction, "reaction_definition" : [f"KEGG Reaction not found (Error: {response_status}"]}
    
    return kegg_reaction_dictionary, responses_string


#pubchem listkeys may speed this up? https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest-tutorial#section=Dealing-with-Lists-of-Identifiers
#may subsequently want to change property to InChI or IsomericSMILES down the line. 
def pubchem_cid_to_descriptor(compound_list, chunk_size = 200):
    df_list = []
    for i in range(0, len(compound_list), chunk_size):
        chunk = compound_list[i:i+chunk_size]
        compound_string = ",".join(chunk)
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{compound_string}/property/CanonicalSMILES/JSON"
        # Fetch JSON data from the URL
        response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Load JSON data
            data = response.json().get("PropertyTable", {}).get("Properties", [])
            df = pd.DataFrame(data)
            df_list.append(df)
        else:
            # If the request was unsuccessful, print an error message
            print("Failed to fetch data. Status code:", response.status_code)
        
    # Convert to DataFrame
    df = pd.concat(df_list)

    return df

def get_kegg_compound_record(kegg_id, compound_cache_dir = None):   
    if compound_cache_dir and os.path.exists(f"{compound_cache_dir}/{kegg_id}.kegg_record.txt"):
        with open(f"{compound_cache_dir}/{kegg_id}.kegg_record.txt", "r") as file:
            compound_record_text = file.read()
    else:
        compound_record = requests.get(f'https://rest.kegg.jp/get/{kegg_id}')
        if compound_record.status_code == 200:
            compound_record_text = compound_record.text
            if compound_cache_dir:
                with open(f"{compound_cache_dir}/{kegg_id}.kegg_record.txt", "w") as file:
                    file.write(compound_record_text)
        else:
            compound_dict = {"compound_id" : kegg_id, "compound_name": None, "dbxrefs": None, "KEGG_compound_record" : None}
            return compound_dict

    compound_record_object = list(Enzyme.parse(io.StringIO(compound_record_text)))[0]
    
    if hasattr(compound_record_object, 'dblinks'):
        dblinks = compound_record_object.dblinks
    else:
        dblinks = []
    if hasattr(compound_record_object, 'name') and len(compound_record_object.name) > 0:
        name = compound_record_object.name[0]
    else:
        name = kegg_id
    compound_dict = {"compound_id" : kegg_id, "compound_name": name, "dbxrefs": dblinks, "KEGG_compound_record" : compound_record_object}
    return compound_dict

def get_kegg_compound_smiles(kegg_id, mol_compound_cache_dir = None):
    if mol_compound_cache_dir and os.path.exists(f"{mol_compound_cache_dir}/{kegg_id}.mol"):
        with open(f"{mol_compound_cache_dir}/{kegg_id}.mol", "r") as file:
            molblock = file.read()
    else:
        time.sleep(1)
        response = requests.get(f'https://rest.kegg.jp/get/{kegg_id}/mol')
        if response.status_code == 200:
            compound_split = response.text.split("> <ENTRY>\n")
            molblock = compound_split[0]
        else:
            molblock = ""
        with open(f"{mol_compound_cache_dir}/{kegg_id}.mol", "w") as file:
            file.write(molblock)
    if molblock == "":   
        canonical_smiles = np.nan
    else:
        canonical_smiles = canon_smiles(Chem.MolFromMolBlock(molblock))
    return canonical_smiles
    
def get_gtc_info(gtcids, cache_df_file):
    glytoucan_df_list = []
    if os.path.exists(cache_df_file):
        cache_df = pd.read_pickle(cache_df_file)
    else:
        cache_df = None
    for gtcid in gtcids:
        if cache_df is not None and gtcid in cache_df.index:
            continue
        else:
            url = 'https://api.glycosmos.org/sparqlist/gtcid2seqs'
            data = {'gtcid': gtcid}
            nested_dict = {}

            response = requests.post(url, data=data)

            if response.status_code == 200:
                json_result = json.loads(response.text)  # Display the response content
                # Iterate through each dictionary in the list
                for item in json_result:
                    id_val = item['id']
                    wurcs_val = item.get('wurcs')
                    glycoct_val = item.get('glycoct')

                    # Check if the ID exists in the nested dictionary
                    if id_val not in nested_dict:
                        # Create a new entry for the ID
                        nested_dict[id_val] = {'wurcs': wurcs_val, 'glycoct': glycoct_val}
                    else:
                        # Update the existing ID entry with non-None values
                        if wurcs_val is not None:
                            nested_dict[id_val]['wurcs'] = wurcs_val
                        if glycoct_val is not None:
                            nested_dict[id_val]['glycoct'] = glycoct_val
                df_dict = pd.DataFrame(nested_dict).T
                glytoucan_df_list.append(df_dict)
            else:
                print(f"Request failed with status code: {response.status_code}")
    if len(glytoucan_df_list) > 0:
        new_gtc_df = pd.concat(glytoucan_df_list)
        gtc_df = pd.concat([cache_df, new_gtc_df])
    else:
        gtc_df = cache_df
    gtc_df.to_pickle(f"{cache_df_file}")
    gtc_df.reset_index(inplace = True)
    return gtc_df

def canon_smiles(x):
        try:
            return Chem.MolToSmiles(x, isomericSmiles = False) #ignore stereochemistry
        except:
            return np.nan
        
from rdkit.Chem import PandasTools

# Function to calculate descriptors
def calculate_descriptors(id, mol, calculator):
    return (id,) + calculator.CalcDescriptors(mol)

def length_upper_sorted(x):
    #sort by length, then favour uppercase starting names
    return sorted(x, key = (lambda y: (len(y) , y.lower() if y[0].islower() else '0' + y.lower())))

def neutralize_atoms(mol):
    """
    Neutralizing Molecules
    Author: Noel O’Boyle (Vincent Scalfani adapted code for RDKit)
    Source: https://baoilleach.blogspot.com/2019/12/no-charge-simple-approach-to.html
    Index ID#: RDKitCB_33
    Summary: Neutralize charged molecules by atom.
    See https://www.rdkit.org/docs/Cookbook.html for more details.
    """
    pattern = Chem.MolFromSmarts("[+1!h0!$([*]~[-1,-2,-3,-4]),-1!$([*]~[+1,+2,+3,+4])]")
    at_matches = mol.GetSubstructMatches(pattern)
    at_matches_list = [y[0] for y in at_matches]
    if len(at_matches_list) > 0:
        for at_idx in at_matches_list:
            atom = mol.GetAtomWithIdx(at_idx)
            chg = atom.GetFormalCharge()
            hcount = atom.GetTotalNumHs()
            atom.SetFormalCharge(0)
            atom.SetNumExplicitHs(hcount - chg)
            atom.UpdatePropertyCache()
    return mol

def parse_brenda_json_generic_reaction(reaction_list):
    ligand_names = []
    for item in reaction_list:
        if item.get("educts"):
            ligand_names.extend(item.get("educts"))
        if item.get("products"):
            ligand_names.extend(item.get("products"))
    return set(ligand_names)

def select_cofactor(cofactor_set):
    if len(cofactor_set) == 1:
            return next(iter(cofactor_set))
    cofactor_set.discard("N")
    cofactor_subgroups = {'Coenzyme', 'Prosthetic Group', 'Siderophore'}
    intersection = cofactor_set & cofactor_subgroups
    
    if len(intersection) == 1:
        return next(iter(intersection))

    return "/".join(sorted(cofactor_set))

def main():    
    """
    This script is designed to take the enzyme.dat file from EXPASY, and extract the EC numbers, 
    and then use the KEGG API to extract the associated EC records, reaction records and compound records.
    The script then searches databases: KEGG, RHEA, ChEBI, PubChem and GlyTouCan for the compound codes, and
    extracts the SMILES strings for each compound. Where possible, duplicate structures are aggregated
    based on their canonical SMILES into a single biological ligand record (with a list of ligand_db identifiers).
    The script then uses the RDKit to calculate molecular descriptors for each ligand, and saves the results
    in a pkl format.
    """

    parser = argparse.ArgumentParser(description='Process EC information.')
    parser.add_argument('--ec_dat', type=str, help='Path to enzyme.dat file from EXPASY')
    parser.add_argument('--enzyme_class_file', type=str, help='Path to enzyme_class file')
    parser.add_argument('--pubchem', type=str, help='Path to pubchem_substance_id_mapping file')
    parser.add_argument('--chebi', type=str, help='Path to chebi_kegg_file')
    parser.add_argument('--rhea_reactions', type=str, help='Path to preprocessed rhea-reaction dataframe')
    parser.add_argument('--kegg_enzyme_string', type=str, default = None, help='Path to kegg_enzyme_strings.txt file, cached from previous run')
    parser.add_argument('--kegg_reaction_string', type=str, default = None, help='Path to kegg_reaction_strings.txt file, cached from previous run')
    parser.add_argument('--smiles_cache', type=str, default = None, help='Path to smiles_cache.pkl file, cached from previous run')
    parser.add_argument('--csdb_cache', type=str, default = None, help='Path to csdb_cache.pkl file, cached from previous run')
    parser.add_argument('--compound_cache_dir', type=str, default = None, help='Path to directory containing KEGG compound records, cached from previous run')
    parser.add_argument('--chebi_relations', type=str, default = None, help='Path to chebi relations.tsv file for extracting cofactor information')
    parser.add_argument('--gtc_cache', type=str, default = None, help='Path to glytoucan_cache.pkl file, cached from previous run')
    args = parser.parse_args()

    if args.compound_cache_dir:
        Path(f"{args.compound_cache_dir}").mkdir(parents=True, exist_ok=True)

    if os.path.exists(f"cognate_ligands_df.pkl"):
        print("Cognate ligands file already exists. Exiting.")
        exit(0)

    ec_records_df = process_ec_records(args.ec_dat , args.enzyme_class_file)

    ec_list = ec_records_df.TRANSFER.unique()
    
    smiles_cache = pd.read_pickle(args.smiles_cache)
    csdb_cache = pd.read_pickle(args.csdb_cache)

    if not os.path.exists(f"kegg_enzyme_df.pkl"):
        print("Getting KEGG Enzyme records")
        n=10 #chunk size
        enzyme_records = {}
        enzyme_string_list = []
        if args.kegg_enzyme_string is not None:
            print("Loading enzyme records from text file.")
            enzyme_dict, enzyme_string = get_kegg_enzymes(ec_list, enzyme_string_file = args.kegg_enzyme_string)
            enzyme_records.update(enzyme_dict)
        else:
            #run this indiviudally, and save the results to a file for each enzyme. Adapt function to take a cache dir and check for matching filename before making api call
            print("Fetching enzyme records from KEGG API")
            for i in range(0, len(ec_list), n):
                print(f"Processing chunk {i} of {len(ec_list)}")
                chunk = ec_list[i:i + n]
                enzyme_dict, enzyme_string = get_kegg_enzymes(chunk)
                enzyme_records.update(enzyme_dict)
                enzyme_string_list.append(enzyme_string)
                time.sleep(1)
            enzyme_string_list_joined = "\n".join(enzyme_string_list)
            with open(f"kegg_enzyme_strings.txt", "w") as file:
                file.write(enzyme_string_list_joined)

        kegg_enzyme_df = pd.DataFrame(enzyme_records).T
        kegg_enzyme_df = kegg_enzyme_df.explode("EC_reactions")
        kegg_enzyme_df.drop(columns = ['reaction_text', 'EC_dbxrefs'], inplace = True)
        kegg_enzyme_df.to_pickle(f"kegg_enzyme_df.pkl")
        print("KEGG Enzyme records saved")
    else:
        kegg_enzyme_df = pd.read_pickle(f"kegg_enzyme_df.pkl")
        print("KEGG Enzyme records loaded from file")
    reactions = kegg_enzyme_df.EC_reactions.dropna().unique()
    #we should first of all compile all of the function outputs into a single text file.
    if not os.path.exists(f"kegg_reaction_df.pkl"):
        #run this indiviudally, and save the results to a file for each enzyme. Adapt function to take a cache dir and check for matching filename before making api call
        print("Getting KEGG Reaction records")
        kegg_reaction_dictionary = {}
        kegg_reaction_strings = []
        if args.kegg_reaction_string is not None:
            print("Loading reaction records from text file.")
            kegg_reaction_dictionary, kegg_reaction_string = get_kegg_reactions(reactions, reactions_string_file = args.kegg_reaction_string)
        else:
            print("Fetching reaction records from KEGG API")
            n=10 #chunk size
            for i in range(0, len(reactions), n):
                chunk = reactions[i:i + n]
                reaction_dictionary, reaction_string = get_kegg_reactions(chunk)
                kegg_reaction_dictionary.update(reaction_dictionary)
                kegg_reaction_strings.append(reaction_string)
                time.sleep(1)
            kegg_reaction_strings_joined = "\n".join(kegg_reaction_strings)
            with open(f"kegg_reaction_strings.txt", "w") as file:
                file.write(kegg_reaction_strings_joined)

        kegg_reaction_df = pd.DataFrame(kegg_reaction_dictionary).T
        assert(len(kegg_reaction_df.loc[kegg_reaction_df.reaction_definition.str.len() > 1]) == 0) #what is this assertion for? 
        kegg_reaction_df = kegg_reaction_df.explode("reaction_definition")
        kegg_reaction_df["reaction_definition"] = kegg_reaction_df.reaction_id + ": " + kegg_reaction_df.reaction_definition
        kegg_reaction_df["reaction_equation"] = kegg_reaction_df.reaction_id + ": " + kegg_reaction_df.reaction_equation
        kegg_reaction_df.to_pickle(f"kegg_reaction_df.pkl")
        print("KEGG Reaction records saved")
    else:
        kegg_reaction_df = pd.read_pickle(f"kegg_reaction_df.pkl")    
        print("KEGG Reaction records loaded from file")
    ##need to have some sort of verification here that the reaction df is based on the same reactions that the enzyme df is based on.

    if not os.path.exists(f"kegg_reaction_enzyme_df.pkl"):
        print("Merging KEGG Enzyme and Reaction records")
        kegg_reaction_enzyme_df = kegg_enzyme_df.merge(kegg_reaction_df, left_on = "EC_reactions", right_on = "reaction_id", how = "left")
        kegg_reaction_enzyme_df["reaction_substrate_codes"] = kegg_reaction_enzyme_df["reaction_substrate_codes"].apply(lambda d: d if isinstance(d, list) else [])
        kegg_reaction_enzyme_df["reaction_product_codes"] = kegg_reaction_enzyme_df["reaction_product_codes"].apply(lambda d: d if isinstance(d, list) else [])
        kegg_reaction_enzyme_df["EC_substrate_codes"] = kegg_reaction_enzyme_df["EC_substrate_codes"].apply(lambda d: d if isinstance(d, list) else [])
        kegg_reaction_enzyme_df["EC_product_codes"] = kegg_reaction_enzyme_df["EC_product_codes"].apply(lambda d: d if isinstance(d, list) else [])

        kegg_reaction_enzyme_df = kegg_reaction_enzyme_df.fillna("").groupby("entry").agg({"entry" : set, "error" : set, "matched_name" : set, "EC_substrate_codes": sum,"EC_product_codes": sum, "reaction_substrate_codes" : sum, "reaction_product_codes": sum, "EC_reactions":set, "reaction_id" : set, "reaction_definition": set, "reaction_equation" : set})
        kegg_reaction_enzyme_df["entities"] = kegg_reaction_enzyme_df["EC_substrate_codes"] + kegg_reaction_enzyme_df["EC_product_codes"] + kegg_reaction_enzyme_df["reaction_substrate_codes"] + kegg_reaction_enzyme_df["reaction_product_codes"]
        kegg_reaction_enzyme_df["entities"] = kegg_reaction_enzyme_df["entities"].apply(lambda x: ",".join(list(set(x))))
        #convert substrate/product codes to a comma separated string instead of list (for easier merging later)
        kegg_reaction_enzyme_df["EC_substrate_codes"] = kegg_reaction_enzyme_df["EC_substrate_codes"].apply(lambda x: ",".join(x))
        kegg_reaction_enzyme_df["EC_product_codes"] = kegg_reaction_enzyme_df["EC_product_codes"].apply(lambda x: ",".join(x))
        kegg_reaction_enzyme_df["reaction_substrate_codes"] = kegg_reaction_enzyme_df["reaction_substrate_codes"].apply(lambda x: ",".join(x))
        kegg_reaction_enzyme_df["reaction_product_codes"] = kegg_reaction_enzyme_df["reaction_product_codes"].apply(lambda x: ",".join(x))
        kegg_reaction_enzyme_df["reaction_definition"] = kegg_reaction_enzyme_df["reaction_definition"].apply(lambda x: ",".join(x))
        kegg_reaction_enzyme_df["reaction_equation"] = kegg_reaction_enzyme_df["reaction_equation"].apply(lambda x: ",".join(x))

        def unpack_sets(row):
            for col in row.index:
                if isinstance(row[col], set) and len(row[col]) == 1:
                    row[col] = next(iter(row[col]))
                elif isinstance(row[col], set) and len(row[col]) > 1:
                    row[col] = list(row[col])
                elif isinstance(row[col], set) and len(row[col]) == 0:
                    row[col] = np.nan
            return row

        kegg_reaction_enzyme_df = kegg_reaction_enzyme_df.apply(unpack_sets, axis=1)
        kegg_reaction_enzyme_df.to_pickle(f"kegg_reaction_enzyme_df.pkl")
        print("KEGG Enzyme and Reaction records merged and saved")
    else:
        kegg_reaction_enzyme_df = pd.read_pickle(f"kegg_reaction_enzyme_df.pkl")
        print("Merged KEGG Enzyme and Reaction records loaded from file")

    kegg_reaction_enzyme_df["entities"] = kegg_reaction_enzyme_df.entities.str.split(",", expand = False)

    #use the coompound codes to filter the pubchem data.
    kegg_reaction_enzyme_df_exploded = kegg_reaction_enzyme_df.explode("entities")
    compound_codes = kegg_reaction_enzyme_df_exploded.entities.dropna().unique()

    #here we should try and get the kegg compounds from the compound codes, where they are non glycans (deal with glycans later)
    if not os.path.exists(f"kegg_compounds_df.pkl"):
        print("Getting KEGG Compound records")
        compound_codes = kegg_reaction_enzyme_df_exploded.entities.dropna().unique()
        kegg_compounds_df = pd.DataFrame([get_kegg_compound_record(code, compound_cache_dir =  args.compound_cache_dir) for code in compound_codes if code.startswith("C")])
        kegg_compounds_df["canonical_smiles"] = kegg_compounds_df["compound_id"].apply(lambda x: get_kegg_compound_smiles(x, mol_compound_cache_dir = args.compound_cache_dir))
        kegg_compounds_df.to_pickle(f"kegg_compounds_df.pkl")
        print("KEGG Compound records saved")
    else:
        kegg_compounds_df = pd.read_pickle(f"kegg_compounds_df.pkl")
        print("KEGG Compound records loaded from file")

    if not os.path.exists(f"kegg_reaction_enzyme_df_exploded_kegg.pkl"):
        print("Merging KEGG Compound records with Enzyme and Reaction records")
        kegg_reaction_enzyme_df_exploded_kegg = kegg_reaction_enzyme_df_exploded.merge(kegg_compounds_df, left_on = "entities", right_on = "compound_id", how = "inner")
        kegg_reaction_enzyme_df_exploded_kegg = kegg_reaction_enzyme_df_exploded_kegg.dropna(subset = ["canonical_smiles"])
        kegg_reaction_enzyme_df_exploded_kegg["ligand_db"] = "KEGG:" + kegg_reaction_enzyme_df_exploded_kegg["entities"].astype("str")
        kegg_reaction_enzyme_df_exploded_kegg["compound_reaction"] = kegg_reaction_enzyme_df_exploded_kegg.apply(lambda x: [re.search(r"^(.+):", item)[1] for item in x.reaction_equation.split(",") if x.compound_id in item], axis = 1)
        kegg_reaction_enzyme_df_exploded_kegg["compound_reaction"] = kegg_reaction_enzyme_df_exploded_kegg["compound_reaction"].str.join("|")
        PandasTools.AddMoleculeColumnToFrame(kegg_reaction_enzyme_df_exploded_kegg, smilesCol='canonical_smiles')
        kegg_reaction_enzyme_df_exploded_kegg.to_pickle(f"kegg_reaction_enzyme_df_exploded_kegg.pkl")
        print("KEGG Compound records merged with Enzyme and Reaction records and saved")
    else:
        kegg_reaction_enzyme_df_exploded_kegg = pd.read_pickle(f"kegg_reaction_enzyme_df_exploded_kegg.pkl")
        print("Merged KEGG Compound records with Enzyme and Reaction records loaded from file")


    #the rhea reactions can have identical molecules on left and right hand side, so should drop duplicates for final df.
    if not args.rhea_reactions:
        raise ValueError("RHEA reactions file not provided")
    else:
        rhea_reactions = pd.read_pickle(args.rhea_reactions)
        rhea_reactions.rename(columns = {"reaction_id": "compound_reaction"}, inplace = True)
        rhea_reactions["compound_reaction"] = rhea_reactions.compound_reaction.apply(lambda x: [x])
        rhea_reactions["compound_reaction"] = rhea_reactions["compound_reaction"].str.join("|")
        print("RHEA records loaded from file")
    ### ChEBI KEGG Mapping
    if not os.path.exists(f"kegg_reaction_enzyme_df_exploded_chebi.pkl"):
        print("Getting ChEBI records")
        chebi_kegg_compounds = pd.read_csv(args.chebi, sep = "\t", index_col = False)
        chebi_kegg_compounds = chebi_kegg_compounds.rename(columns = {"ID" : "ChEBI_ID", "NAME" : "ChEBI_NAME"})
        chebi_kegg_compounds_smiles = chebi_kegg_compounds.loc[chebi_kegg_compounds.SMILES.isna() == False]
        ### Merging ChEBI with enzyme df

        kegg_reaction_enzyme_df_exploded_chebi = kegg_reaction_enzyme_df_exploded.merge(chebi_kegg_compounds_smiles, left_on = "entities", right_on = "KEGG COMPOUND ACCESSION", how = "inner", indicator = True)
        kegg_reaction_enzyme_df_exploded_chebi.drop(columns = "_merge", inplace = True)
        kegg_reaction_enzyme_df_exploded_chebi = kegg_reaction_enzyme_df_exploded_chebi.loc[kegg_reaction_enzyme_df_exploded_chebi.SMILES.isna() == False].copy()

        PandasTools.AddMoleculeColumnToFrame(kegg_reaction_enzyme_df_exploded_chebi, smilesCol='SMILES')
        kegg_reaction_enzyme_df_exploded_chebi = kegg_reaction_enzyme_df_exploded_chebi.loc[kegg_reaction_enzyme_df_exploded_chebi.ROMol.isna() == False].reset_index(drop = True)

        kegg_reaction_enzyme_df_exploded_chebi["ligand_db"] = kegg_reaction_enzyme_df_exploded_chebi["ChEBI_ID"].astype("str")
        kegg_reaction_enzyme_df_exploded_chebi["compound_reaction"] = kegg_reaction_enzyme_df_exploded_chebi.apply(lambda x: [re.search(r"^(.+):", item)[1] for item in x.reaction_equation.split(",") if x["KEGG COMPOUND ACCESSION"] in item], axis = 1)
        kegg_reaction_enzyme_df_exploded_chebi["compound_reaction"] = kegg_reaction_enzyme_df_exploded_chebi["compound_reaction"].str.join("|")
        kegg_reaction_enzyme_df_exploded_chebi = kegg_reaction_enzyme_df_exploded_chebi.loc[kegg_reaction_enzyme_df_exploded_chebi.ROMol.isna() == False].reset_index(drop = True)
        kegg_reaction_enzyme_df_exploded_chebi.to_pickle(f"kegg_reaction_enzyme_df_exploded_chebi.pkl")
        print("ChEBI records saved")
    else:
        kegg_reaction_enzyme_df_exploded_chebi = pd.read_pickle(f"kegg_reaction_enzyme_df_exploded_chebi.pkl")    
        print("ChEBI records loaded from file")

    if not os.path.exists(f"kegg_reaction_enzyme_df_exploded_pubchem.pkl"):
        print("Getting PubChem records")
        ### PubChem KEGG Mapping from here : https://pubchem.ncbi.nlm.nih.gov/source/
        with open(args.pubchem, 'r') as file:
            lines = file.readlines()
            
        data = []
        for line in lines:
            record = {}
            line = line.replace(": ", ":")
            parts = line.strip().split()  # Split line by space
            for part in parts:
                key, value = part.split(':')  # Split by colon and space to get key-value pairs
                record[key] = value
            data.append(record)

        kegg_pubchem_mapping = pd.DataFrame(data)
        pubchem_kegg_compound_records = pd.DataFrame([get_kegg_compound_record(code, compound_cache_dir = args.compound_cache_dir) for code in kegg_pubchem_mapping.KEGG.unique()])
        kegg_pubchem_mapping = kegg_pubchem_mapping.merge(pubchem_kegg_compound_records, left_on = "KEGG", right_on = "compound_id", how = "left", indicator = True)
        assert(len(kegg_pubchem_mapping.loc[kegg_pubchem_mapping._merge != "both"]) == 0)
        kegg_pubchem_mapping.drop(columns = ["_merge"], inplace = True)
        cids = kegg_pubchem_mapping.loc[(kegg_pubchem_mapping.CID.isna() == False) &
                                        (kegg_pubchem_mapping.KEGG.isin(compound_codes))].CID.unique()

        pubchem_smiles = pubchem_cid_to_descriptor(cids)

        kegg_pubchem_mapping["CID"] = kegg_pubchem_mapping["CID"].fillna(0).astype(int)
        pubchem_smiles["CID"] = pubchem_smiles["CID"].astype(int)

        kegg_pubchem_mapping_smiles = kegg_pubchem_mapping.merge(pubchem_smiles, on = "CID", how = "left", indicator = True)
        kegg_pubchem_mapping_smiles_filtered = kegg_pubchem_mapping_smiles.loc[kegg_pubchem_mapping_smiles.CanonicalSMILES.isna() == False].reset_index(drop = True).copy()
        kegg_pubchem_mapping_smiles_filtered.drop(columns = "_merge", inplace = True)

        ### Merging PubChem with enzyme df
        kegg_reaction_enzyme_df_exploded_pubchem = kegg_reaction_enzyme_df_exploded.merge(kegg_pubchem_mapping_smiles_filtered, left_on = "entities", right_on = "KEGG", how = "inner")
        PandasTools.AddMoleculeColumnToFrame(kegg_reaction_enzyme_df_exploded_pubchem, smilesCol='CanonicalSMILES')

        kegg_reaction_enzyme_df_exploded_pubchem = kegg_reaction_enzyme_df_exploded_pubchem.loc[kegg_reaction_enzyme_df_exploded_pubchem.ROMol.isna() == False].reset_index(drop = True)
        kegg_reaction_enzyme_df_exploded_pubchem["ligand_db"] = "Pubchem:" + kegg_reaction_enzyme_df_exploded_pubchem["CID"].astype("str")
        kegg_reaction_enzyme_df_exploded_pubchem["compound_reaction"] = kegg_reaction_enzyme_df_exploded_pubchem.apply(lambda x: [re.search(r"^(.+):", item)[1] for item in x.reaction_equation.split(",") if x.compound_id in item], axis = 1)
        kegg_reaction_enzyme_df_exploded_pubchem["compound_reaction"] = kegg_reaction_enzyme_df_exploded_pubchem["compound_reaction"].str.join("|")
        kegg_reaction_enzyme_df_exploded_pubchem.to_pickle(f"kegg_reaction_enzyme_df_exploded_pubchem.pkl")
    else:
        print("PubChem records loaded from file")
        kegg_reaction_enzyme_df_exploded_pubchem = pd.read_pickle(f"kegg_reaction_enzyme_df_exploded_pubchem.pkl")


    if not os.path.exists(f"kegg_reaction_enzyme_df_exploded_gtc.pkl"):
        ### Getting list of glytoucan glycans to query
        glycans = kegg_reaction_enzyme_df_exploded.loc[(kegg_reaction_enzyme_df_exploded.entities.isna() == False) 
                                                        & (kegg_reaction_enzyme_df_exploded.entities.str.startswith("G")), "entities"].values.tolist()

        ### Getting KEGG compound records for glycans (to get xref to glytoucan)
        glycan_compounds = []

        for glycan in glycans:
            compound = get_kegg_compound_record(glycan, compound_cache_dir=args.compound_cache_dir)
            glycan_compounds.append(compound)
            
        glycan_compounds_df = pd.DataFrame(glycan_compounds)
        glycan_compounds_df[["source", "secondary_id"]] = glycan_compounds_df.apply(lambda x: extract_secondary_id(x["compound_id"], x["dbxrefs"]), axis = 1, result_type = "expand").values
        glytoucan_ids = glycan_compounds_df.loc[(glycan_compounds_df.secondary_id.isna() == False) &
                                        (glycan_compounds_df.source == "GlyTouCan"), "secondary_id"].unique()

        glytoucan_df = get_gtc_info(glytoucan_ids, cache_df_file = f"{args.gtc_cache}")

        glycan_compounds_df_merged = glycan_compounds_df.merge(glytoucan_df, left_on = "secondary_id", right_on = "index", how = "left")

        #now need to convert this through into an smiles representation.
        #convert to csdb linear and then smiles
        glycan_compounds_df_merged["csdb"] = glycan_compounds_df_merged.glycoct.apply(lambda x: get_csdb_from_glycoct(x, csdb_cache))
        new_csdb_values = glycan_compounds_df_merged.loc[(glycan_compounds_df_merged.glycoct.isin(csdb_cache.glycoct.values) == False) & (glycan_compounds_df_merged.glycoct.isna() == False), ["csdb","glycoct"]].drop_duplicates()
        csdb_cache = pd.concat([csdb_cache, new_csdb_values], ignore_index = True)
        csdb_cache.to_pickle(f"{args.csdb_cache}")
        glycan_compounds_df_merged["smiles"] = glycan_compounds_df_merged.apply(lambda x: get_smiles_from_csdb(x["csdb"], smiles_cache), axis = 1)
        new_smiles_values = glycan_compounds_df_merged.loc[glycan_compounds_df_merged.csdb.isin(smiles_cache.csdb.values) == False, ["smiles","csdb"]].drop_duplicates()
        new_smiles_values.rename(columns = {"smiles":"descriptor"}, inplace = True)
        smiles_cache = pd.concat([smiles_cache, new_smiles_values], ignore_index = True)
        smiles_cache.to_pickle(f"{args.smiles_cache}")
        glycan_compounds_df_merged = glycan_compounds_df_merged.loc[glycan_compounds_df_merged.smiles.isna() == False]
        kegg_reaction_enzyme_df_exploded_gtc = kegg_reaction_enzyme_df_exploded.merge(glycan_compounds_df_merged, left_on="entities", right_on="compound_id", how = "inner")
        PandasTools.AddMoleculeColumnToFrame(kegg_reaction_enzyme_df_exploded_gtc, smilesCol='smiles')

        kegg_reaction_enzyme_df_exploded_gtc = kegg_reaction_enzyme_df_exploded_gtc.loc[kegg_reaction_enzyme_df_exploded_gtc.ROMol.isna() == False].reset_index(drop = True)
        kegg_reaction_enzyme_df_exploded_gtc["ligand_db"] = "GlyTouCan:" + kegg_reaction_enzyme_df_exploded_gtc["secondary_id"].astype("str")
        kegg_reaction_enzyme_df_exploded_gtc["compound_reaction"] = kegg_reaction_enzyme_df_exploded_gtc.apply(lambda x: [re.search(r"^(.+):", item)[1] for item in x.reaction_equation.split(",") if x.compound_id in item], axis = 1)
        kegg_reaction_enzyme_df_exploded_gtc["compound_reaction"] = kegg_reaction_enzyme_df_exploded_gtc["compound_reaction"].str.join("|")
        kegg_reaction_enzyme_df_exploded_gtc.to_pickle(f"kegg_reaction_enzyme_df_exploded_gtc.pkl")
        print("GlyTouCan records saved")
    else:
        print("GlyTouCan records loaded from file")
        kegg_reaction_enzyme_df_exploded_gtc = pd.read_pickle(f"kegg_reaction_enzyme_df_exploded_gtc.pkl")

    if not os.path.exists(f"cognate_ligands_df.pkl"):
        cognate_ligands_df = pd.concat([rhea_reactions[["entry", "compound_id", "compound_name", "ROMol", "ligand_db", "compound_reaction"]],
                                           kegg_reaction_enzyme_df_exploded_kegg[["entry", "compound_name", "compound_id", "ROMol", "ligand_db", "compound_reaction"]], 
                                           kegg_reaction_enzyme_df_exploded_chebi[["entry", "ChEBI_NAME", "KEGG COMPOUND ACCESSION", "ROMol", "ligand_db", "compound_reaction"]].rename(columns = {"KEGG COMPOUND ACCESSION" : "compound_id"}), 
                                           kegg_reaction_enzyme_df_exploded_pubchem[["entry", "compound_name", "KEGG", "ROMol", "ligand_db", "compound_reaction"]].rename(columns = {"KEGG" : "compound_id"}),
                                           kegg_reaction_enzyme_df_exploded_gtc[["entry", "compound_name", "compound_id","ROMol", "ligand_db", "compound_reaction"]]])
        cognate_ligands_df = cognate_ligands_df.reset_index()
        
        #fill the missing compound names first using the chebi name, and subsequently with the compound id if that is also nan.
        cognate_ligands_df["compound_name"] = cognate_ligands_df["compound_name"].fillna(cognate_ligands_df["ChEBI_NAME"]).fillna(cognate_ligands_df["compound_id"])
        cognate_ligands_df["ROMol"] = cognate_ligands_df["ROMol"].apply(lambda x: neutralize_atoms(x) if isinstance(x,Chem.rdchem.Mol) else np.nan) #attempt to neutralise charged structures for grouping as charges cannot be used to score mols
        cognate_ligands_df["canonical_smiles"] = cognate_ligands_df["ROMol"].map(lambda x: canon_smiles(x) if isinstance(x,Chem.rdchem.Mol) else np.nan)
        cognate_ligands_df_unique_smiles = cognate_ligands_df[["canonical_smiles", "compound_name", "ligand_db", "compound_reaction"]].copy()
        cognate_ligands_df_unique_smiles["compound_reaction"] = cognate_ligands_df_unique_smiles["compound_reaction"].fillna("")
        cognate_ligands_df_unique_smiles = cognate_ligands_df_unique_smiles.groupby("canonical_smiles", dropna = False).agg({"compound_name": set, "ligand_db": set, "compound_reaction": set}).reset_index()
        cognate_ligands_df_unique_smiles["ligand_db"] = cognate_ligands_df_unique_smiles.ligand_db.str.join("|")
        cognate_ligands_df_unique_smiles["compound_name"] = cognate_ligands_df_unique_smiles.compound_name.str.join("|")
        cognate_ligands_df_unique_smiles["compound_reaction"] = cognate_ligands_df_unique_smiles.compound_reaction.str.join("|").str.strip("|")
        cognate_ligands_df_unique_smiles = cognate_ligands_df_unique_smiles.reset_index(drop=True).reset_index()

        cognate_ligands_df_unique_smiles.rename(columns = {"index": "uniqueID"}, inplace = True)
        cognate_ligands_df = cognate_ligands_df[["entry", "canonical_smiles"]].merge(cognate_ligands_df_unique_smiles, on = "canonical_smiles", how = "left")
        cognate_ligands_df["compound_name"] = cognate_ligands_df["compound_name"].str.split("|").apply(lambda x: length_upper_sorted(x)).str.join("|")
        cognate_ligands_df = cognate_ligands_df.drop_duplicates()
        
        chebi_relations = pd.read_csv(f"{args.chebi_relations}", sep="\t")

        chebi_cofactors = chebi_relations.loc[(chebi_relations.TYPE == "has_role") & (chebi_relations.INIT_ID.isin([23357,23354,26348,26672])), ["TYPE", "INIT_ID", "FINAL_ID"]]
        chebi_cofactors.loc[chebi_cofactors.INIT_ID == 23357, "TYPE"] = "Cofactor"
        chebi_cofactors.loc[chebi_cofactors.INIT_ID == 23354, "TYPE"] = "Coenzyme"
        chebi_cofactors.loc[chebi_cofactors.INIT_ID == 26348, "TYPE"] = "Prosthetic Group"
        chebi_cofactors.loc[chebi_cofactors.INIT_ID == 26672, "TYPE"] = "Siderophore"
        chebi_cofactors.drop(columns = ["INIT_ID"], inplace = True)
        chebi_cofactors.rename(columns = {"TYPE": "isCofactor"}, inplace = True)
        

        chebi_matches = cognate_ligands_df.ligand_db.str.extractall("CHEBI:([0-9]+)").astype("float")
        chebi_matches_grouped = chebi_matches.groupby(level=0)[0].apply(list)
        chebi_matches_grouped.rename("chebi_match", inplace = True)
        cognate_ligands_df = cognate_ligands_df.merge(chebi_matches_grouped, left_index = True, right_index = True, how = "left")
        cognate_ligands_df = cognate_ligands_df.explode("chebi_match")
        cognate_ligands_df = cognate_ligands_df.merge(chebi_cofactors, how = "left", left_on = "chebi_match", right_on = "FINAL_ID")
        cognate_ligands_df["isCofactor"] = cognate_ligands_df["isCofactor"].fillna("N")
        cognate_ligands_df.drop(columns = ["chebi_match", "FINAL_ID"], inplace = True)
        cognate_ligands_df = cognate_ligands_df.groupby([col for col in cognate_ligands_df if col != "isCofactor"]).agg({"isCofactor":set}).reset_index()
        cognate_ligands_df["isCofactor"] = cognate_ligands_df["isCofactor"].apply(lambda x: select_cofactor(x))
        cognate_ligands_df.to_pickle(f"cognate_ligands_df.pkl")
    else:
        cognate_ligands_df = pd.read_pickle(f"cognate_ligands_df.pkl")

if __name__ == "__main__":
    main()
    
#glygen??