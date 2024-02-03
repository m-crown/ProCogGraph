#!/usr/bin/env python
from pdbecif.mmcif_io import CifFileReader
from Bio.ExPASy import Enzyme as EEnzyme
from pathlib import Path
import requests
import os
from pprint import pprint # for later pretty printing only
import numpy as np
from utils import get_terminal_record, get_csdb_from_glycoct, get_glycoct_from_wurcs, get_smiles_from_csdb
import json
from urllib.parse import quote
import pandas as pd
import xml.etree.ElementTree as ET
import re
import argparse
from bs4 import BeautifulSoup
import yaml

def return_partial_EC_list(ec, total_ec_list):
    if not isinstance(ec, str) and np.isnan(ec):
        return np.nan
    elif "-" in ec:
        replacement_character = r'.'
        modified_ec = re.sub(r'\.', r"_", ec)
        modified_ec = modified_ec.replace("-", ".")
        total_ec_list = [re.sub(r'\.', r"_", item) for item in total_ec_list]
        # Use re.match() to check if the modified string matches any item in the match_list
        matching_ec = [ec for ec in total_ec_list if re.match(modified_ec, ec)]
        matching_ec = [re.sub(r'_', r".", item) for item in matching_ec]
        return(matching_ec)
    else:
        return [ec]

def get_updated_enzyme_records(df, ec_records_df, ec_col = "protein_entity_ec"):
    ec_list = ec_records_df.ID.unique()
    
    residue_ec_records = df[[ec_col]].drop_duplicates()
    residue_ec_records["protein_entity_ec_copy"] = residue_ec_records[ec_col]
    residue_ec_records["protein_entity_ec_copy"] = residue_ec_records.protein_entity_ec_copy.str.split(",")
    residue_ec_records = residue_ec_records.explode("protein_entity_ec_copy")
    residue_ec_records["protein_entity_ec_copy"] = residue_ec_records.protein_entity_ec_copy.str.strip()
    residue_ec_records["ec_list"] = residue_ec_records.protein_entity_ec_copy.apply(lambda x: return_partial_EC_list(x, ec_list))
    residue_ec_records = residue_ec_records.explode("ec_list")
    residue_ec_records = residue_ec_records.merge(ec_records_df[["ID", "TRANSFER"]], left_on = "ec_list", right_on = "ID", how = "left")
    residue_ec_records["TRANSFER"] = residue_ec_records["TRANSFER"].fillna("")

    # anythin with NAN now in ID/transfer doesnt actually exist in the expasy enzyme list - so is incorrect.

    residue_ec_records_grouped = residue_ec_records.groupby(ec_col).agg({"TRANSFER": set}).reset_index()
    residue_ec_records_grouped["TRANSFER"] = residue_ec_records_grouped["TRANSFER"].apply(lambda x: ",".join(x) if x != "" else "")
    residue_ec_records_grouped.rename(columns = {"TRANSFER" : "ec_list"}, inplace = True)
    
    df_merged = df.merge(residue_ec_records_grouped, on = ec_col, how = "left", indicator = True)
    assert(len(df_merged.loc[df_merged["_merge"] != "both"]) == 0)
    df_merged.drop(columns = "_merge", inplace = True)
    return(df_merged)

from neo4j import __version__ as neo4j_version,  GraphDatabase
print(f"Neo4j python package version: {neo4j_version}")
#class is from https://towardsdatascience.com/neo4j-cypher-python-7a919a372be7
import pandas as pd
class Neo4jConnection:
    
    def __init__(self, uri, user, pwd):
        self.__uri = uri
        self.__user = user
        self.__pwd = pwd
        self.__driver = None
        try:
            self.__driver = GraphDatabase.driver(self.__uri, auth=(self.__user, self.__pwd))
        except Exception as e:
            print("Failed to create the driver:", e)
        
    def close(self):
        if self.__driver is not None:
            self.__driver.close()
        
    def query(self, query, db=None):
        assert self.__driver is not None, "Driver not initialized!"
        session = None
        response = None
        try: 
            session = self.__driver.session(database=db) if db is not None else self.__driver.session() 
            response = list(session.run(query))
        except Exception as e:
            print("Query failed:", e)
        finally: 
            if session is not None:
                session.close()
        return response

def parse_table_data(elem):
    data = {}
    for row in elem.findall('row'):
        row_data = {}
        for field in row.findall('field'):
            row_data[field.attrib['name']] = field.text
        data[len(data)] = row_data
    return data

def main():

    parser = argparse.ArgumentParser(description = 'TO DO')
    parser.add_argument('--neo4j_bolt_uri', default = 'bolt://localhost:7687', type = str,
        help = "")
    parser.add_argument('--neo4j_user', default = 'neo4j', type = str,
        help = "")
    parser.add_argument('--neo4j_password', type = str,
        help = "")
    parser.add_argument('--outdir', type = str, default = "parity_calcs",
        help = ""),
    parser.add_argument('--enzyme_dat_file', type = str, default = "enzyme.dat",
        help = ""),
    parser.add_argument('--pdbe_graph_yaml', type = str, default = "pdbe_graph.yaml",
        help = "")
    
    args = parser.parse_args()

    print("Connecting to neo4j")
    conn = Neo4jConnection(uri=f"{args.neo4j_bolt_uri}", user=f"{args.neo4j_user}", pwd=f"{args.neo4j_password}")
    print("Connected to neo4j")
    print("Generating EC record dataframe")
    with open(f"{args.enzyme_dat_file}") as handle:
        ec_records = EEnzyme.parse(handle)
        ec_records_list = []
        for record in ec_records: 
            ec_record_series = pd.Series(record)
            ec_records_list.append(ec_record_series)


    ec_records_df = pd.DataFrame(ec_records_list)
    ec_records_df["TRANSFER"] = ec_records_df.apply(lambda x: get_terminal_record(x["ID"], x, ec_records_df), axis = 1)
    ec_records_df["TRANSFER"] = ec_records_df["TRANSFER"].fillna(ec_records_df.ID)

    #how do we store the neo4j cypher queries? in a separate file? yaml?
    #should consider how we can use the symmetry operator information to condense this down? multiple bound molecules can conist of the same bound ligands, differentiated by SYM_OPERATOR
    #in the bl instances, we are not making use of the symmetry operator information. Or is it covered by having the bm info there?
    
    
    #from https://stackoverflow.com/questions/1773805/how-can-i-parse-a-yaml-file-in-python
    with open(f"{args.pdbe_graph_yaml}", "r") as stream:
        try:
            pdbe_graph_queries = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

    cath_pdb_residue_interactions_query_distinct_bl = pdbe_graph_queries["cath_bl_query"]
    cath_pdb_residue_interactions_query_distinct_sugar = pdbe_graph_queries["cath_sugar_query"]
    scop_pdb_residue_interactions_query_distinct_bl = pdbe_graph_queries["scop_bl_query"]
    scop_pdb_residue_interactions_query_distinct_sugar = pdbe_graph_queries["scop_sugar_query"]
    interpro_pdb_residue_interactions_query_distinct_bl_d = pdbe_graph_queries["interpro_d_bl_query"] 
    interpro_pdb_residue_interactions_query_distinct_sugar_d = pdbe_graph_queries["interpro_d_sugar_query"]
    interpro_pdb_residue_interactions_query_distinct_bl_f = pdbe_graph_queries["interpro_f_bl_query"]
    interpro_pdb_residue_interactions_query_distinct_sugar_f = pdbe_graph_queries["interpro_f_sugar_query"]
    interpro_pdb_residue_interactions_query_distinct_bl_h = pdbe_graph_queries["interpro_h_bl_query"]
    interpro_pdb_residue_interactions_query_distinct_sugar_h = pdbe_graph_queries["interpro_h_sugar_query"]

    Path(f"{args.outdir}").mkdir(parents=True, exist_ok=True)

    if not os.path.exists(f"{args.outdir}/bound_molecules_ligands.csv.gz"):
        if not os.path.exists(f"{args.outdir}/cath_pdb_residue_interactions_distinct_bl.csv.gz"):
            print("Retrieving cath_pdb_residue_interactions_distinct_bl")
            cath_pdb_residue_interactions_distinct_bl = pd.DataFrame([dict(_) for _ in conn.query(cath_pdb_residue_interactions_query_distinct_bl, db='neo4j')])
            cath_pdb_residue_interactions_distinct_bl.to_csv(f"{args.outdir}/cath_pdb_residue_interactions_distinct_bl.csv.gz", compression = "gzip")
        else:
            print("Loading cath_pdb_residue_interactions_distinct_bl")
            cath_pdb_residue_interactions_distinct_bl = pd.read_csv(f"{args.outdir}/cath_pdb_residue_interactions_distinct_bl.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

        if not os.path.exists(f"{args.outdir}/scop_pdb_residue_interactions_distinct_bl.csv.gz"):
            print("Retrieving scop_pdb_residue_interactions_distinct_bl")
            scop_pdb_residue_interactions_distinct_bl = pd.DataFrame([dict(_) for _ in conn.query(scop_pdb_residue_interactions_query_distinct_bl, db='neo4j')])
            scop_pdb_residue_interactions_distinct_bl.to_csv(f"{args.outdir}/scop_pdb_residue_interactions_distinct_bl.csv.gz", compression = "gzip")
        else:
            print("Loading scop_pdb_residue_interactions_distinct_bl")
            scop_pdb_residue_interactions_distinct_bl = pd.read_csv(f"{args.outdir}/scop_pdb_residue_interactions_distinct_bl.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
        
        if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl.csv.gz"):
            if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_d.csv.gz"):
                print("Retrieving interpro_pdb_residue_interactions_distinct_bl_d")
                interpro_pdb_residue_interactions_distinct_bl_d = pd.DataFrame([dict(_) for _ in conn.query(interpro_pdb_residue_interactions_query_distinct_bl_d, db='neo4j')])
                interpro_pdb_residue_interactions_distinct_bl_d.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_d.csv.gz", compression = "gzip")
            else:
                print("Loading interpro_pdb_residue_interactions_distinct_bl_d")
                interpro_pdb_residue_interactions_distinct_bl_d = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_d.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
            
            if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_f.csv.gz"):
                print("Retrieving interpro_pdb_residue_interactions_distinct_bl_f")
                interpro_pdb_residue_interactions_distinct_bl_f = pd.DataFrame([dict(_) for _ in conn.query(interpro_pdb_residue_interactions_query_distinct_bl_f, db='neo4j')])
                interpro_pdb_residue_interactions_distinct_bl_f.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_f.csv.gz", compression = "gzip")
            else:
                print("Loading interpro_pdb_residue_interactions_distinct_bl_f")
                interpro_pdb_residue_interactions_distinct_bl_f = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_f.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

            if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_h.csv.gz"):
                print("Retrieving interpro_pdb_residue_interactions_distinct_bl_h")
                interpro_pdb_residue_interactions_distinct_bl_h = pd.DataFrame([dict(_) for _ in conn.query(interpro_pdb_residue_interactions_query_distinct_bl_h, db='neo4j')])
                interpro_pdb_residue_interactions_distinct_bl_h.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_h.csv.gz", compression = "gzip")
            else:
                print("Loading interpro_pdb_residue_interactions_distinct_bl_h")
                interpro_pdb_residue_interactions_distinct_bl_h = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_h.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
            interpro_pdb_residue_interactions_distinct_bl = pd.concat([interpro_pdb_residue_interactions_distinct_bl_d,
                                                                    interpro_pdb_residue_interactions_distinct_bl_f,
                                                                    interpro_pdb_residue_interactions_distinct_bl_h])
            interpro_pdb_residue_interactions_distinct_bl.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl.csv.gz", compression = "gzip")

        print("Updating ligand EC records")
        cath_pdb_residue_interactions_distinct_bl_ec = get_updated_enzyme_records(cath_pdb_residue_interactions_distinct_bl, ec_records_df)
        scop_pdb_residue_interactions_distinct_bl_ec = get_updated_enzyme_records(scop_pdb_residue_interactions_distinct_bl, ec_records_df)
        interpro_pdb_residue_interactions_distinct_bl_ec = get_updated_enzyme_records(interpro_pdb_residue_interactions_distinct_bl, ec_records_df)

        cath_pdb_residue_interactions_distinct_bl_ec["uniqueID"] = cath_pdb_residue_interactions_distinct_bl_ec["bound_molecule_id"] + "_" + cath_pdb_residue_interactions_distinct_bl_ec["bound_ligand_id"].astype("str")
        cath_pdb_residue_interactions_distinct_bl_ec["type"] = "ligand"
        scop_pdb_residue_interactions_distinct_bl_ec["uniqueID"] = scop_pdb_residue_interactions_distinct_bl_ec["bound_molecule_id"] + "_" + scop_pdb_residue_interactions_distinct_bl_ec["bound_ligand_id"].astype("str")
        scop_pdb_residue_interactions_distinct_bl_ec["type"] = "ligand"
        interpro_pdb_residue_interactions_distinct_bl_ec["uniqueID"] = interpro_pdb_residue_interactions_distinct_bl_ec["bound_molecule_id"] + "_" + interpro_pdb_residue_interactions_distinct_bl_ec["bound_ligand_id"].astype("str")
        interpro_pdb_residue_interactions_distinct_bl_ec["type"] = "ligand"

        cath_pdb_residue_interactions_distinct_bl_ec.to_csv(f"{args.outdir}/cath_pdb_residue_interactions_distinct_bl_ec.csv.gz", index = False, compression = "gzip")
        scop_pdb_residue_interactions_distinct_bl_ec.to_csv(f"{args.outdir}/scop_pdb_residue_interactions_distinct_bl_ec.csv.gz", index = False, compression = "gzip")
        interpro_pdb_residue_interactions_distinct_bl_ec.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_bl_ec.csv.gz", index = False, compression = "gzip")
        
        bound_molecules_ligands = pd.concat([cath_pdb_residue_interactions_distinct_bl_ec[["bound_molecule_id", "bound_ligand_id"]].drop_duplicates(), scop_pdb_residue_interactions_distinct_bl_ec[["bound_molecule_id", "bound_ligand_id"]].drop_duplicates(),
            interpro_pdb_residue_interactions_distinct_bl_ec[["bound_molecule_id", "bound_ligand_id"]].drop_duplicates()])
        print("Saving bound_molecules_ligands")
        bound_molecules_ligands.to_csv(f"{args.outdir}/bound_molecules_ligands.csv.gz", index = False, compression = "gzip")

    else:
        print("Loading bound_molecules_ligands")
        bound_molecules_ligands = pd.read_csv(f"{args.outdir}/bound_molecules_ligands.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
        
    if not os.path.exists(f"{args.outdir}/bound_molecules_sugars.csv.gz"):
    
        if not os.path.exists(f"{args.outdir}/cath_pdb_residue_interactions_distinct_sugar.csv.gz"):
            print("Retrieving cath_pdb_residue_interactions_distinct_sugar")
            cath_pdb_residue_interactions_distinct_sugar = pd.DataFrame([dict(_) for _ in conn.query(cath_pdb_residue_interactions_query_distinct_sugar, db='neo4j')])
            cath_pdb_residue_interactions_distinct_sugar.to_csv(f"{args.outdir}/cath_pdb_residue_interactions_distinct_sugar.csv.gz", compression = "gzip")
        else:
            print("Loading cath_pdb_residue_interactions_distinct_sugar")
            cath_pdb_residue_interactions_distinct_sugar = pd.read_csv(f"{args.outdir}/cath_pdb_residue_interactions_distinct_sugar.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

        if not os.path.exists(f"{args.outdir}/scop_pdb_residue_interactions_distinct_sugar.csv.gz"):
            print("Retrieving scop_pdb_residue_interactions_distinct_sugar")
            scop_pdb_residue_interactions_distinct_sugar = pd.DataFrame([dict(_) for _ in conn.query(scop_pdb_residue_interactions_query_distinct_sugar, db='neo4j')])
            scop_pdb_residue_interactions_distinct_sugar.to_csv(f"{args.outdir}/scop_pdb_residue_interactions_distinct_sugar.csv.gz", compression = "gzip")
        else:
            print("Loading scop_pdb_residue_interactions_distinct_sugar")
            scop_pdb_residue_interactions_distinct_sugar = pd.read_csv(f"{args.outdir}/scop_pdb_residue_interactions_distinct_sugar.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

        if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar.csv.gz"):
            if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_d.csv.gz"):
                print("Retrieving interpro_pdb_residue_interactions_distinct_sugar_d")
                interpro_pdb_residue_interactions_distinct_sugar_d = pd.DataFrame([dict(_) for _ in conn.query(interpro_pdb_residue_interactions_query_distinct_sugar_d, db='neo4j')])
                interpro_pdb_residue_interactions_distinct_sugar_d.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_d.csv.gz", compression = "gzip")
            else:
                print("Loading interpro_pdb_residue_interactions_distinct_sugar_d")
                interpro_pdb_residue_interactions_distinct_sugar_d = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_d.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

            if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_f.csv.gz"):
                print("Retrieving interpro_pdb_residue_interactions_distinct_sugar_f")
                interpro_pdb_residue_interactions_distinct_sugar_f = pd.DataFrame([dict(_) for _ in conn.query(interpro_pdb_residue_interactions_query_distinct_sugar_f, db='neo4j')])
                interpro_pdb_residue_interactions_distinct_sugar_f.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_f.csv.gz", compression = "gzip")
            else:
                print("Loading interpro_pdb_residue_interactions_distinct_sugar_f")
                interpro_pdb_residue_interactions_distinct_sugar_f = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_f.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
            
            if not os.path.exists(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_h.csv.gz"):
                print("Retrieving interpro_pdb_residue_interactions_distinct_sugar_h")
                interpro_pdb_residue_interactions_distinct_sugar_h = pd.DataFrame([dict(_) for _ in conn.query(interpro_pdb_residue_interactions_query_distinct_sugar_h, db='neo4j')])
                interpro_pdb_residue_interactions_distinct_sugar_h.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_h.csv.gz", compression = "gzip")
            else:
                print("Loading interpro_pdb_residue_interactions_distinct_sugar_h")
                interpro_pdb_residue_interactions_distinct_sugar_h = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_h.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
        
            interpro_pdb_residue_interactions_distinct_sugar = pd.concat([interpro_pdb_residue_interactions_distinct_sugar_d,
                                                                    interpro_pdb_residue_interactions_distinct_sugar_f,
                                                                    interpro_pdb_residue_interactions_distinct_sugar_h])
            interpro_pdb_residue_interactions_distinct_sugar.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar.csv.gz", compression = "gzip")
        else:
            print("Loading interpro_pdb_residue_interactions_distinct_sugar")
            interpro_pdb_residue_interactions_distinct_sugar = pd.read_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

        print("Updating sugar EC records")
        cath_pdb_residue_interactions_distinct_sugar_ec = get_updated_enzyme_records(cath_pdb_residue_interactions_distinct_sugar, ec_records_df)
        scop_pdb_residue_interactions_distinct_sugar_ec = get_updated_enzyme_records(scop_pdb_residue_interactions_distinct_sugar, ec_records_df)
        interpro_pdb_residue_interactions_distinct_sugar_ec = get_updated_enzyme_records(interpro_pdb_residue_interactions_distinct_sugar, ec_records_df)

        cath_pdb_residue_interactions_distinct_sugar_ec["uniqueID"] = cath_pdb_residue_interactions_distinct_sugar_ec["bound_molecule_id"] + "_se" + cath_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"].astype("str")
        cath_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"] = cath_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"].astype(int)
        cath_pdb_residue_interactions_distinct_sugar_ec["type"] = "sugar"
        scop_pdb_residue_interactions_distinct_sugar_ec["uniqueID"] = scop_pdb_residue_interactions_distinct_sugar_ec["bound_molecule_id"] + "_se" + scop_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"].astype("str")
        scop_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"] = scop_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"].astype(int)
        scop_pdb_residue_interactions_distinct_sugar_ec["type"] = "sugar"
        interpro_pdb_residue_interactions_distinct_sugar_ec["uniqueID"] = interpro_pdb_residue_interactions_distinct_sugar_ec["bound_molecule_id"] + "_se" + interpro_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"].astype("str")
        interpro_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"] = interpro_pdb_residue_interactions_distinct_sugar_ec["ligand_entity_id_numerical"].astype(int)
        interpro_pdb_residue_interactions_distinct_sugar_ec["type"] = "sugar"

        cath_pdb_residue_interactions_distinct_sugar_ec.to_csv(f"{args.outdir}/cath_pdb_residue_interactions_distinct_sugar_ec.csv.gz", index = False, compression = "gzip")
        scop_pdb_residue_interactions_distinct_sugar_ec.to_csv(f"{args.outdir}/scop_pdb_residue_interactions_distinct_sugar_ec.csv.gz", index = False, compression = "gzip")
        interpro_pdb_residue_interactions_distinct_sugar_ec.to_csv(f"{args.outdir}/interpro_pdb_residue_interactions_distinct_sugar_ec.csv.gz", index = False, compression = "gzip")

        #verifying that the sugar bound ligand ids are not in the bound ligand dataframes.
        assert(len(cath_pdb_residue_interactions_distinct_sugar_ec.loc[cath_pdb_residue_interactions_distinct_sugar_ec.bound_ligand_id.isin(bound_molecules_ligands.bound_ligand_id.unique())]) == 0)
        assert(len(scop_pdb_residue_interactions_distinct_sugar_ec.loc[scop_pdb_residue_interactions_distinct_sugar_ec.bound_ligand_id.isin(bound_molecules_ligands.bound_ligand_id.unique())]) == 0)
        assert(len(interpro_pdb_residue_interactions_distinct_sugar_ec.loc[interpro_pdb_residue_interactions_distinct_sugar_ec.bound_ligand_id.isin(bound_molecules_ligands.bound_ligand_id.unique())]) == 0)

        bound_molecules_sugars = pd.concat([
            cath_pdb_residue_interactions_distinct_sugar_ec[["pdb_id", "bound_molecule_id", "ligand_entity_id", "uniqueID", "ligand_entity_description", "ligand_entity_id_numerical", "protein_entity_ec"]].drop_duplicates(), 
            scop_pdb_residue_interactions_distinct_sugar_ec[["pdb_id", "bound_molecule_id", "ligand_entity_id", "uniqueID", "ligand_entity_description", "ligand_entity_id_numerical", "protein_entity_ec"]].drop_duplicates(),
            interpro_pdb_residue_interactions_distinct_sugar_ec[["pdb_id", "bound_molecule_id", "ligand_entity_id", "uniqueID", "ligand_entity_description", "ligand_entity_id_numerical", "protein_entity_ec"]].drop_duplicates()
            ])
        bound_molecules_sugars.to_csv(f"{args.outdir}/bound_molecules_sugars.csv.gz", index = False, compression = "gzip")
    else:
        print("Loading bound_molecules_sugars")
        bound_molecules_sugars = pd.read_csv(f"{args.outdir}/bound_molecules_sugars.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)
    
    if not os.path.exists(f"{args.outdir}/bound_molecules_sugars_ec_exploded.csv.gz"):
        print("retrieving sugar CIF records")

        cif_ids = bound_molecules_sugars.pdb_id.unique()
        Path(f"{args.outdir}/sugar_cifs").mkdir(parents=True, exist_ok=True)
        for cif_id in cif_ids:
            cif_path = f"{args.outdir}/sugar_cifs/{cif_id}_updated.cif"
            if not os.path.exists(cif_path):
                response = requests.get(f'http://www.ebi.ac.uk/pdbe/entry-files/download/{cif_id}_updated.cif')
                
                with open(cif_path, 'wb') as fp:
                    fp.write(response.content)

        
        branched_entity_list = []
        reader = CifFileReader()
        for cif_id in cif_ids:
            cif_path = f'sugar_cifs/{cif_id}_updated.cif'
            cif_dict = reader.read(cif_path, output='cif_dictionary')
            cif_df = pd.DataFrame(cif_dict)
            if "_pdbx_entity_branch_descriptor" in cif_df.index:
                branch_data = cif_df.loc["_pdbx_entity_branch_descriptor"].values[0]
                if type(next(iter(branch_data.values()))) == str:  # If only one descriptor
                    branched_entity_descriptors = pd.DataFrame({key: [value] for key, value in branch_data.items()})  # Convert scalar value to DataFrame
                else:  # If multiple descriptors
                    branched_entity_descriptors = pd.DataFrame(branch_data)
                branched_entity_descriptors["pdb_id"] = cif_id

                branched_entity_list.append(branched_entity_descriptors)
                
        branched_entity_df = pd.concat(branched_entity_list)
        branched_entity_df["entity_id"] = branched_entity_df.entity_id.astype("int")
        branched_entity_df.loc[branched_entity_df.type == "WURCS"].pdb_id.nunique()

        sugar_wurcs = branched_entity_df.loc[branched_entity_df.type == "WURCS"].groupby(["pdb_id", "entity_id"]).head(1).reset_index()

        sugar_wurcs.rename(columns = {"descriptor" : "WURCS"}, inplace = True)

        bound_molecules_sugars = bound_molecules_sugars.merge(sugar_wurcs[["entity_id", "WURCS", "pdb_id"]], left_on = ["pdb_id", "ligand_entity_id_numerical"], right_on = ["pdb_id", "entity_id"], how = "left", indicator = True)

        bound_molecules_sugars.loc[bound_molecules_sugars._merge != "both", "WURCS"] = "WURCS not available"
        bound_molecules_sugars.drop(columns = ["_merge"], inplace = True)

        bound_molecules_sugars_ec = get_updated_enzyme_records(bound_molecules_sugars, ec_records_df, ec_col = "protein_entity_ec")
        
        bound_molecules_sugars_ec["ec_list"] = bound_molecules_sugars_ec.ec_list.str.split(",")
        bound_molecules_sugars_ec = bound_molecules_sugars_ec.explode("ec_list")
        bound_molecules_sugars_ec.drop(columns = "protein_entity_ec", inplace = True)
        bound_molecules_sugars_ec.to_csv(f"{args.outdir}/bound_molecules_sugars_ec_exploded.csv.gz", compression = "gzip")
    else:
        print("Loading bound_molecules_sugars_ec_exploded")
        bound_molecules_sugars_ec = pd.read_csv(f"{args.outdir}/bound_molecules_sugars_ec_exploded.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

    if not os.path.exists(f"{args.outdir}/bound_molecules_sugars_smiles.pkl"):
        print("retrieving sugar smiles")
        if not os.path.exists(f"{args.outdir}/bound_sugars_to_score.pkl"):
            bound_sugars_to_score = bound_molecules_sugars_ec.loc[bound_molecules_sugars_ec.WURCS != "WURCS not available", ["ligand_entity_description","WURCS", "ec_list"]].drop_duplicates()
            bound_sugars_to_score = bound_sugars_to_score.groupby(["ligand_entity_description","WURCS"]).agg({"ec_list": set}).reset_index()

            bound_sugars_to_score["glycoct"] = bound_sugars_to_score["WURCS"].apply(lambda x: get_glycoct_from_wurcs(x))
            bound_sugars_to_score = bound_sugars_to_score.loc[bound_sugars_to_score.glycoct.isna() == False]

            bound_sugars_to_score["csdb"] = bound_sugars_to_score["glycoct"].apply(lambda x: get_csdb_from_glycoct(x))
            bound_sugars_to_score["descriptor"] = bound_sugars_to_score["csdb"].apply(lambda x: get_smiles_from_csdb(x))

            bound_sugars_to_score = bound_sugars_to_score.loc[bound_sugars_to_score.descriptor.isna() == False]

            bound_sugars_to_score = bound_sugars_to_score.reset_index()
            bound_sugars_to_score.drop(columns = ["index"], inplace = True)
            bound_sugars_to_score = bound_sugars_to_score.reset_index().rename(columns = {"index": "ligand_index"})

            bound_molecules_sugars_ec = bound_molecules_sugars_ec.merge(bound_sugars_to_score[["ligand_entity_description", "ligand_index", "WURCS", "descriptor"]], on = ["ligand_entity_description","WURCS"], how = "left")

            bound_sugars_to_score["bl_name"] = bound_sugars_to_score["ligand_entity_description"]
            bound_sugars_to_score.rename(columns = {"ligand_index": "ligand_entity_id"}, inplace = True) #do this to run sugars in parity calcs
            bound_sugars_to_score.to_pickle(f"{args.outdir}/bound_sugars_to_score.pkl")
        else:
            print("Loading bound_sugars_to_score")
            bound_sugars_to_score = pd.read_pickle(f"{args.outdir}/bound_sugars_to_score.pkl")

        missing_ligand_index = bound_molecules_sugars_ec.loc[bound_molecules_sugars_ec.descriptor.isna(), ["pdb_id", "entity_id"]].drop_duplicates()
        missing_ligand_index["missing_ligand_index"] = missing_ligand_index.reset_index(drop=True).reset_index().index + bound_molecules_sugars_ec.ligand_index.max() + 1

        bound_molecules_sugars_ec = bound_molecules_sugars_ec.merge(missing_ligand_index, on = ["pdb_id", "entity_id"], how = "left")
        bound_molecules_sugars_ec["ligand_index"].fillna(bound_molecules_sugars_ec["missing_ligand_index"], inplace=True)
        bound_molecules_sugars_ec.drop(columns = "missing_ligand_index", inplace = True)
        bound_molecules_sugars_ec["descriptor"].fillna("SMILES unavailable", inplace = True)

        bound_molecules_sugars_ec.to_pickle(f"{args.outdir}/bound_molecules_sugars_smiles.pkl")
    else:
        print("Loading bound_molecules_sugars_smiles")
        bound_molecules_sugars_ec = pd.read_pickle(f"{args.outdir}/bound_molecules_sugars_smiles.pkl")
        bound_sugars_to_score = pd.read_pickle(f"{args.outdir}/bound_sugars_to_score.pkl")

    if not os.path.exists(f"{args.outdir}/bound_entities_to_score.pkl"):
        print("retrieving ligand smiles")
        #should potentially move this part of the script to the yaml fiel that others come from.
        if not os.path.exists(f"{args.outdir}/all_chem_descriptors_bm_ec.csv.gz"):
            if not os.path.exists(f"{args.outdir}/all_chem_descriptors_bm.csv.gz"):
                all_chem_descriptors_query_bm = pdbe_graph_queries["all_chem_descriptors_bm"]

                all_chem_descriptors_bm = pd.DataFrame([dict(_) for _ in conn.query(all_chem_descriptors_query_bm, db='neo4j')])
                all_chem_descriptors_bm.to_csv(f"{args.outdir}/all_chem_descriptors_bm.csv.gz", compression = "gzip")
            else:
                print("Loading all_chem_descriptors_bm")
                all_chem_descriptors_bm = pd.read_csv(f"{args.outdir}/all_chem_descriptors_bm.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

            all_chem_descriptors_ec = get_updated_enzyme_records(all_chem_descriptors_bm, ec_records_df, ec_col = "protein_polymer_EC")
            all_chem_descriptors_ec["ec_list"] = all_chem_descriptors_ec.ec_list.str.split(",")
            all_chem_descriptors_ec = all_chem_descriptors_ec.explode("ec_list")
            all_chem_descriptors_ec.drop(columns = "protein_polymer_EC", inplace = True)
            all_chem_descriptors_ec.to_csv(f"{args.outdir}/all_chem_descriptors_bm_ec.csv.gz", compression = "gzip")
        else:
            print("Loading all_chem_descriptors_bm_ec")
            all_chem_descriptors_ec = pd.read_csv(f"{args.outdir}/all_chem_descriptors_bm_ec.csv.gz", compression = "gzip", na_values = ["NaN", "None"], keep_default_na = False)

        all_chem_descriptors_smiles = all_chem_descriptors_ec.loc[all_chem_descriptors_ec.descriptor_type == "SMILES_CANONICAL"]
        all_chem_descriptors_smiles_unique_pairs = all_chem_descriptors_smiles.drop_duplicates(["bl_id","ec_list"], keep='first') #get the unique pairs of inchi descriptors and EC numbers

        
        bound_ligand_descriptors = all_chem_descriptors_smiles_unique_pairs.loc[
            (all_chem_descriptors_smiles_unique_pairs.bl_id.isin(bound_molecules_ligands.bound_ligand_id.unique()))]

        bound_ligands_to_score = bound_ligand_descriptors[["ligand_entity_description", "bl_name", "descriptor", "ec_list"]].drop_duplicates()
        bound_ligands_to_score = bound_ligands_to_score.groupby(["bl_name", "descriptor"]).agg({"ec_list": set, "ligand_entity_description": "first"}).reset_index()
        bound_ligands_to_score = bound_ligands_to_score.reset_index().rename(columns = {"index" : "ligand_entity_id"})
        bound_ligands_to_score["ligand_entity_id"] = bound_ligands_to_score["ligand_entity_id"] + bound_molecules_sugars_ec.ligand_index.max() + 1 #plus one because of 0 index to avoid overlaps
        bound_ligands_to_score.to_pickle(f"{args.outdir}/bound_ligands_to_score.pkl")

        bound_ligand_descriptors =  bound_ligand_descriptors.merge(bound_ligands_to_score[["bl_name", "descriptor", "ligand_entity_id"]].rename(columns = {"ligand_entity_id":"ligand_index"}), on = ["bl_name", "descriptor"], how = "left", indicator = True)
        assert(len(bound_ligand_descriptors.loc[bound_ligand_descriptors._merge != "both"]) == 0)
        bound_ligand_descriptors.drop(columns = "_merge", inplace = True)
        bound_ligand_descriptors.to_pickle(f"{args.outdir}/bound_ligand_descriptors.pkl")

        bound_entities_to_score = pd.concat([bound_sugars_to_score[["ligand_entity_id", "bl_name", "ligand_entity_description", "descriptor", "ec_list"]], bound_ligands_to_score])
        bound_entities_to_score.to_pickle(f"{args.outdir}/bound_entities_to_score.pkl")

    else:
        print("Loading bound_entities_to_score")
        bound_ligands_to_score = pd.read_pickle(f"{args.outdir}/bound_entities_to_score.pkl")

    #consider dropping the retrieval of ligand_entity_id from graph. We remove it in the domain_ownership script anyway.
    #also consider using a different name to ligand_entity_id for the index in scoring - can even do ligand index , just need to update the scoring script for this change.
    #now do a summary of all the data before exiting.

if __name__ == "__main__":
    main()