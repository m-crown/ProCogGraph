#!/usr/bin/env python

from gemmi import cif
import pandas as pd
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import gzip
import numpy as np
from itertools import chain
import sys
import re 
def extract_data(elem):
    data = []
    if elem.get("type") == "protein":
        chain_id = elem.get("entityId")
        for segment in elem:
            list_residues = segment.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}listResidue')
            for res_list in list_residues:
                residues = res_list.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}residue')
                for residue in residues:
                    resnum = residue.get('dbResNum')
                    dbxrefs = residue.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}crossRefDb')
                    for dbxref in dbxrefs:
                        dbxref_value = None
                        if dbxref.get("dbSource") == "InterPro":
                            if dbxref.get("dbEvidence").startswith("SSF") or dbxref.get("dbEvidence").startswith("G3DSA"):
                                dbxref_value = dbxref.get("dbEvidence")
                                row = {"chainID": chain_id, "resNum": int(resnum), "dbSource": dbxref.get("dbSource"), "dbAccessionId": dbxref.get("dbAccessionId"), "dbxref": dbxref_value}
                                data.append(row)
                        elif dbxref.get("dbSource") in ["CATH", "Pfam", "SCOP2B"]:
                            row = {"chainID": chain_id, "resNum": int(resnum), "dbSource": dbxref.get("dbSource"), "dbAccessionId": dbxref.get("dbAccessionId"), "dbxref": dbxref_value}
                            data.append(row)
    data_df = pd.DataFrame(data)
    return data_df

def sort_numeric_with_inscode(tosort):
    numeric_split = [re.findall(r'(\d+)_*(\D*)', item) for item in tosort] # Find all numeric parts in the string (we define format as numeric_inscode) - keep the underscore outside of the split to remove this 
    sorted_parts = sorted(numeric_split, key=lambda x: int(x[0][0]))  # Sort numeric parts (each item in the original list is broken into a one item list where the first item is the numeric item to be sorted by)
    return '|'.join([''.join(tup for tup in sorted_parts_list[0]) for sorted_parts_list in sorted_parts])  # Concat numeric and non-numeric parts

def assign_ownership_percentile_categories(ligands_df, unique_id = "uniqueID", domain_grouping_key = "cath_domain", database_type = None, preassigned = False):
    if database_type:
        total_group_key = [unique_id, database_type]
        domain_group_key = [unique_id, domain_grouping_key, database_type]
    else:
        total_group_key = [unique_id]
        domain_group_key = [unique_id, domain_grouping_key]
    if not preassigned: #for pdbe-graph extracted data we assign counts in func. 
        ligands_df["total_contact_counts"]  =  ligands_df.groupby(total_group_key)["contact_type_count"].transform("sum")
        ligands_df[["domain_contact_counts", "domain_hbond_counts", "domain_covalent_counts"]]  = ligands_df.groupby(domain_group_key)[["contact_type_count", "hbond_count", "covalent_count"]].transform("sum")
        ligands_df["domain_hbond_perc"] = ligands_df.domain_hbond_counts / ligands_df.total_contact_counts
        ligands_df["domain_contact_perc"] = ligands_df.domain_contact_counts / ligands_df.total_contact_counts
        ligands_df["num_non_minor_domains"] = ligands_df.groupby([unique_id])["domain_contact_perc"].transform(lambda x: len(x[x > 0.1]))
    ligands_df["domain_ownership"] = np.where(
        ligands_df["domain_contact_perc"] == 1, "exclusive",
        np.where(
            ligands_df["domain_contact_perc"] >= 0.9, "dominant",
            np.where(
                (ligands_df["domain_contact_perc"] >= 0.5)
                & (ligands_df["domain_contact_perc"] < 0.9) & (ligands_df["num_non_minor_domains"] == 1), "major",
                np.where(
                (ligands_df["domain_contact_perc"] >= 0.5)
                & (ligands_df["domain_contact_perc"] < 0.9) & (ligands_df["num_non_minor_domains"] > 1), "major_partner",
                    np.where(
                    (ligands_df["domain_contact_perc"] > 0.1)
                    & (ligands_df["domain_contact_perc"] < 0.5) & (ligands_df["num_non_minor_domains"] > 1), "partner",
                        np.where(
                        ligands_df["domain_contact_perc"] <= 0.1, "minor", np.nan)
                    )
                )
            )
        )
    )
    
    return ligands_df

def pattern_to_range(pattern):
    start, end = map(int, re.search(r'(\d+)-(\d+)', pattern).groups())
    return ",".join([str(x) for x in range(start, end + 1)])

def main():
    """
    Extracts domain information from the updated MMCIF file and assigns ownership categories to ligands based on domain contact percentages
    derived from pdbe-arpeggio.
    Is expected to fail if:
        1. No contacts are found between the ligand and any protein entity (e.g. only to DNA) (exitcode 124)
        2. No contacts are present within an annotated domain (exitcode 125)
        3. No domains are present for any protein entities in the assembly (exitcode 126)
        4. No contacts remain at minimum contact count (exitcode 127)
    """

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--cif', type=str, help='cif file containing PDBe updated structure, may be gzipped')
    parser.add_argument('--bound_entity_pickle', type=str, help='pickle file of bound entity info from cif file')
    parser.add_argument('--contacts', type=str, help='json file of contacts from pdbe-arpeggio')
    parser.add_argument('--pdb_id', type=str, help='pdb id of the structure')
    parser.add_argument('--assembly_id', type=str, help='assembly id of the structure')
    parser.add_argument('--domain_contact_cutoff' , type = int, default = 3, help = 'minimum number of contacts for a domain to be considered')
    parser.add_argument('--sifts_xml', type=str, help='sifts xml file (gzipped)')
    args = parser.parse_args()

    doc = cif.read(args.cif)
    block = doc.sole_block()

    #load the previously generated bound entity info
    bound_entity_info_grouped = pd.read_pickle(args.bound_entity_pickle)
    bound_entity_info_grouped_residue_list = bound_entity_info_grouped["arpeggio"].explode().values
    #generate pdb info and entity descriptions from cif file
    pdb_info_list = [args.pdb_id] + [block.find_value(item) for item in ["_struct.pdbx_descriptor", "_struct.title", "_struct_keywords.pdbx_keywords"]]
    pdb_info_series = pd.Series(pdb_info_list, index = ["pdb_id", "pdb_descriptor", "pdb_title", "pdb_keywords"])
    pdb_info_series = pdb_info_series.str.strip("\"|'")

    ##see this webinar for details https://pdbeurope.github.io/api-webinars/webinars/web5/arpeggio.html
    assembly_info = pd.DataFrame(block.find(['_pdbx_struct_assembly_gen.assembly_id', '_pdbx_struct_assembly_gen.oper_expression', '_pdbx_struct_assembly_gen.asym_id_list']), columns = ["assembly_id", "oper_expression", "asym_id_list"])
    assembly_info = assembly_info.loc[assembly_info.assembly_id == args.assembly_id].copy() #preferred assembly id
    #some structures have a range in the format '(1-60)' - expand this before splitting, see 1al0 for example, some structures have a range in the format 1-60, see 6rjf for example
    #so, first strip all brackets from the oper expression and then expand the range
    assembly_info["oper_expression"] = assembly_info["oper_expression"].str.strip("()'")
    assembly_info.loc[assembly_info["oper_expression"].str.match("\d+-\d+"), "oper_expression"] = assembly_info.loc[assembly_info["oper_expression"].str.match("\d+-\d+"), "oper_expression"].apply(pattern_to_range)
    #observe some ; and \n in asym_id_list (see 3hye for example) -  so strip ; and \n; from start and end of string before splitting - will expand this if necessary on more errors
    assembly_info["oper_expression"] = assembly_info["oper_expression"].str.strip("\n;")
    assembly_info["oper_expression"] = assembly_info["oper_expression"].str.split(",")
    assembly_info["asym_id_list"] = assembly_info["asym_id_list"].str.strip("\n;").str.split(",") #asym id here is the struct
    assembly_info_exploded = assembly_info.explode("oper_expression").explode("asym_id_list").rename(columns = {"asym_id_list": "struct_asym_id"})
    #the oper_expression for the identity operation does not receive an _[digit] suffix, so we need to remove the oper_expression from it - see 2r9p for example or 4cr7
    #this is necessary for matching the pdb-h format
    oper_list = pd.DataFrame(block.find(['_pdbx_struct_oper_list.id', '_pdbx_struct_oper_list.type']), columns = ["oper_expression_id", "type"])

    assembly_info_exploded_oper = assembly_info_exploded.merge(oper_list, left_on = "oper_expression", right_on = "oper_expression_id", how = "left", indicator = True)
    assert(len(assembly_info_exploded_oper.loc[assembly_info_exploded_oper._merge != "both"]) == 0)
    assembly_info_exploded_oper.loc[assembly_info_exploded_oper.type == "'identity operation'", "oper_expression"] = ""
    assembly_info_exploded_oper.drop(columns = ["oper_expression_id", "type" , "_merge"], inplace = True)

    struct_auth_asym_mapping = pd.DataFrame(block.find(['_atom_site.label_entity_id', '_atom_site.label_asym_id', '_atom_site.auth_asym_id']), columns = ["protein_entity_id","chain_id", "auth_asym_id"]).drop_duplicates()

    #parse the possible protein entities for combining with contacts data 
    #https://bioinformatics.stackexchange.com/questions/11587/what-is-the-aim-of-insertion-codes-in-the-pdb-file-format
    poly_entity_df = pd.DataFrame(block.find(["_entity_poly.entity_id", "_entity_poly.type"]), columns = ["protein_entity_id", "type"])
    poly_entity_df["type"] = poly_entity_df["type"].str.strip("\"'")
    protein_entity_df = poly_entity_df.loc[poly_entity_df.type.str.startswith("polypeptide"), ["protein_entity_id"]].copy()
    protein_entity_df["pdb_id"] = pdb_info_series.loc["pdb_id"]
    protein_entity_df_auth_merge = protein_entity_df.merge(struct_auth_asym_mapping, on = "protein_entity_id", how = "left", indicator = True)
    ##assert(len(protein_entity_df_auth_merge.loc[protein_entity_df_auth_merge._merge == "left_only"]) == 0)
    ##protein_entity_df_auth_merge.drop(columns = ["_merge"], inplace = True)
    protein_entity_df_auth_merge.rename(columns = {"auth_asym_id": "auth_chain_id", "chain_id":"proteinStructAsymID"}, inplace = True)

    protein_entity_df_assembly = protein_entity_df_auth_merge.merge(assembly_info_exploded_oper[["oper_expression", "struct_asym_id"]], left_on = "proteinStructAsymID", right_on = "struct_asym_id", how = "inner") #inner to keep only entities in the assembly
    #assert(len(protein_entity_df_assembly.loc[protein_entity_df_assembly._merge != "both"]) == 0)
    protein_entity_df_assembly.drop(columns = ["struct_asym_id"], inplace = True)
    protein_entity_df_assembly["assembly_chain_id_protein"] = protein_entity_df_assembly["auth_chain_id"] + "_" + protein_entity_df_assembly["oper_expression"] 
    protein_entity_df_assembly["assembly_chain_id_protein"] = protein_entity_df_assembly["assembly_chain_id_protein"].str.strip("_")
    protein_entity_df_assembly.drop(columns = ["_merge", "oper_expression"], inplace = True)

    #parse the domain information from the updated mmcif file
    domain_info_dataframe = pd.DataFrame(block.find("_pdbx_sifts_xref_db_segments.", ["entity_id", "asym_id", "xref_db", "xref_db_acc", "domain_name", "segment_id", "instance_id", "seq_id_start", "seq_id_end"]), 
            columns = ["entity_id", "asym_id", "xref_db", "xref_db_acc", "domain_name", "segment_id", "instance_id", "seq_id_start", "seq_id_end"])
    ##for now, we are ready to handle annotations from CATH, SCOP, SCOP2B, Pfam and InterPro, so we filter to this
    ##we check in process_pdb_structure that domains are present for the structure, so no need to fail here.
    domain_info_dataframe = pd.DataFrame(block.find("_pdbx_sifts_xref_db_segments.", ["entity_id", "asym_id", "xref_db", "xref_db_acc", "domain_name", "segment_id", "instance_id", "seq_id_start", "seq_id_end"]), 
        columns = ["entity_id", "asym_id", "xref_db", "xref_db_acc", "domain_name", "segment_id", "instance_id", "seq_id_start", "seq_id_end"])
    domain_info_dataframe_filtered = domain_info_dataframe.loc[domain_info_dataframe.xref_db.isin(["CATH", "SCOP", "SCOP2B", "Pfam", "InterPro"])]
    if len(domain_info_dataframe_filtered) > 0:    
        #when cath database is referenced, the db_accession we care about is the domain_name - so fill this
        domain_info_dataframe_filtered.loc[domain_info_dataframe_filtered.xref_db == "CATH", "xref_db_acc"] = domain_info_dataframe_filtered.loc[domain_info_dataframe_filtered.xref_db == "CATH", "domain_name"] 
        domain_info_dataframe_filtered["seq_range"] = domain_info_dataframe_filtered.apply(lambda x: range(int(x.seq_id_start), int(x.seq_id_end) + 1), axis = 1)
        domain_info_dataframe_filtered_grouped = domain_info_dataframe_filtered.groupby([col for col in domain_info_dataframe_filtered.columns if col not in ["seq_id_start", "seq_id_end","segment_id", "seq_range"]]).agg({"seq_range": list}).reset_index() #group by all columns except seq and segment - aggregate segments into a list.
        #multiple domain instances can occur - we just aggregate the seq ranges for each instance.
        #assert(domain_info_dataframe_filtered_grouped.instance_id.astype(int).max() == 1) #assertion to flag when this isnt the case - we have no test examples of this
        
        domain_info_dataframe_filtered_grouped["seq_range_chain"] = domain_info_dataframe_filtered_grouped["seq_range"].apply(lambda x: list(chain(*x)))
        domain_info_dataframe_filtered_grouped.drop(columns = ["domain_name","seq_range", "instance_id"], inplace = True) #drop instance id now that assertion has passed - if this fails need to investigate struct

        protein_entity_df_assembly_domain_mmcif = protein_entity_df_assembly.merge(domain_info_dataframe_filtered_grouped, left_on = ["protein_entity_id", "proteinStructAsymID"], right_on = ["entity_id","asym_id"], how = "inner")
        protein_entity_df_assembly_domain_mmcif.drop(columns = ["entity_id", "asym_id"],inplace = True)
        protein_entity_df_assembly_domain_mmcif["seq_range_chain"] = protein_entity_df_assembly_domain_mmcif["seq_range_chain"].apply(lambda x: ",".join([str(z) for z in sorted(set([int(y) for y in x]))])) #to match the xml data format
        mmcif_domains = domain_info_dataframe_filtered_grouped.xref_db.unique()
    else:
        protein_entity_df_assembly_domain_mmcif = pd.DataFrame()
        mmcif_domains = []
    ##THE UPDATED MMCIF FILE DOES NOT CONTAIN A FULL SET OF DOMAIN INFORMATION, WE NEED TO USE THE PDBE SIFTS XML DATA FILES TO GET ANY DB SOURCES NOT REFERENCED IN THE UPDATED MMCIF
    # WE PREFER THE UPDATED MMCIF REFERENCES WHERE POSSIBLE DUE TO THEIR RICHER ANNOTATION DETAIL FOR E.G. CATH DOMAINS WHERE SPECIFIC DOMAINS ARE REFERENCED INSTEAD OF HOMOLOGOUS SUPERFAMILIES.
    with gzip.open(args.sifts_xml, 'rb') as f:
        tree = ET.parse(f)
        root = tree.getroot()

    entity_id_list = []
    db_resnum_list = []
    dbsource_list = []
    dbaccessionid_list = []

    # Iterate over entities
    for entity in root.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}entity'):
        entity_id = entity.attrib['entityId']
        # Iterate over all segments and listresidues in segments 
        for segment in entity.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}segment'):
            # Iterate over listResidue elements
            for residue in segment.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}residue'):
                db_resnum = residue.attrib['dbResNum']
                # search crossrefdb for matching dbs
                for crossRefDb in residue.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}crossRefDb'):
                    dbsource = crossRefDb.attrib['dbSource']
                    if dbsource in ["CATH", "Pfam", "SCOP", "SCOP2B"] and dbsource not in mmcif_domains:
                        dbaccessionid = crossRefDb.attrib['dbAccessionId']
                    elif dbsource == "InterPro" and dbsource not in mmcif_domains:
                        dbevidence = crossRefDb.attrib['dbEvidence']
                        if dbevidence.startswith("SSF") or dbevidence.startswith("G3DSA"):
                            dbaccessionid = crossRefDb.attrib['dbAccessionId'] + "_" + dbevidence
                        else:
                            continue
                    else:
                        continue
                    # get db data in lists
                    entity_id_list.append(entity_id)
                    db_resnum_list.append(db_resnum)
                    dbsource_list.append(dbsource)
                    dbaccessionid_list.append(dbaccessionid)

    # convert to dataframe
    domain_df = pd.DataFrame({
        'proteinStructAsymID': entity_id_list,
        'seq_range_chain': db_resnum_list,
        'xref_db': dbsource_list,
        'xref_db_acc': dbaccessionid_list
    })

    # aggregate db resnum to lists 
    domain_df_grouped = domain_df.groupby(['proteinStructAsymID', 'xref_db', 'xref_db_acc'])['seq_range_chain'].agg(list).reset_index()


    #get db specific info
    db_source_list = []
    db_version_list = []

    # parse db info
    for db_list in root.findall('.//{http://www.ebi.ac.uk/pdbe/docs/sifts/eFamily.xsd}listDB'):
        for db in db_list: 
            db_source = db.attrib['dbSource']
            db_version = db.attrib['dbVersion']
            db_source_list.append(db_source)
            db_version_list.append(db_version)

    # convert to df 
    db_df = pd.DataFrame({
        'xref_db': db_source_list,
        'xref_db_version': db_version_list
    })

    if len(domain_df_grouped.loc[domain_df_grouped.xref_db == "InterPro"]) > 0:
        domain_df_grouped.loc[domain_df_grouped.xref_db == "InterPro", "xref_db_acc"] = domain_df_grouped.loc[domain_df_grouped.xref_db == "InterPro", "xref_db_acc"].str.split("_")
        domain_info_df_exploded = domain_df_grouped.explode("xref_db_acc")
    else:
        domain_info_df_exploded = domain_df_grouped

    domain_info_df_exploded = domain_info_df_exploded.drop_duplicates(subset = ["proteinStructAsymID","xref_db","xref_db_acc"])
    domain_info_df_exploded["seq_range_chain"] = domain_info_df_exploded["seq_range_chain"].apply(lambda x: ",".join([str(z) for z in sorted(set([int(y) for y in x]))]))#.str.join(",") #sometimes the information per residue is duplicated in sifts xml. join for dropping duplicates then resplit
    domain_info_df_exploded.drop_duplicates()

    protein_entity_df_assembly_domain_xml = domain_info_df_exploded.merge(protein_entity_df_assembly, on = "proteinStructAsymID", how = "inner") #keep the chains in the assembly which have domain information (but not domains in chains not in the assembly)
    protein_entity_df_assembly_domain_mmcif["domain_type"] = "mmcif"
    protein_entity_df_assembly_domain_xml["domain_type"] = "xml"

    protein_entity_df_assembly_domain = pd.concat([protein_entity_df_assembly_domain_mmcif, protein_entity_df_assembly_domain_xml], ignore_index = True)

    # combine with domain info df
    protein_entity_df_assembly_domain = pd.merge(protein_entity_df_assembly_domain, db_df, on='xref_db', how='left')

    if len(protein_entity_df_assembly_domain) == 0:
        #domain that exists in the updated mmcif structure is for a chain that isnt present in the assembly - 6ba1 chain D versus assembly A and E for example
        print(f"Domains do not exist for any protein entities in the assembly for {args.pdb_id}")
        sys.exit(126)

    protein_entity_df_assembly_domain["seq_range_chain"] = protein_entity_df_assembly_domain["seq_range_chain"].apply(lambda x: [int(y) for y in x.split(",")])
    protein_entity_df_assembly_domain.loc[(protein_entity_df_assembly_domain.xref_db == "InterPro") & (protein_entity_df_assembly_domain.xref_db_acc.str.startswith("G3DSA")), "xref_db"] = "G3DSA"
    protein_entity_df_assembly_domain.loc[(protein_entity_df_assembly_domain.xref_db == "G3DSA") & (protein_entity_df_assembly_domain.xref_db_acc.str.startswith("G3DSA")), "xref_db_acc"] = protein_entity_df_assembly_domain.loc[(protein_entity_df_assembly_domain.xref_db == "G3DSA") & (protein_entity_df_assembly_domain.xref_db_acc.str.startswith("G3DSA")), "xref_db_acc"].str.replace("^G3DSA:", "", regex = True)
    protein_entity_df_assembly_domain.loc[(protein_entity_df_assembly_domain.xref_db == "InterPro") & (protein_entity_df_assembly_domain.xref_db_acc.str.startswith("SSF")), "xref_db"] = "SuperFamily"

    #need to map auth id's for protein entities to seq ids for domain ranges
    seq_sites = pd.DataFrame(block.find(['_atom_site.label_entity_id', '_atom_site.label_asym_id', '_atom_site.label_seq_id', '_atom_site.auth_asym_id', '_atom_site.auth_seq_id', '_atom_site.pdbx_PDB_ins_code']), columns = ["protein_entity_id","chain_id", "seq_id", "auth_asym_id", "auth_seq_id", "pdb_ins_code"]).drop_duplicates()
    protein_seq_sites = seq_sites.loc[seq_sites.protein_entity_id.isin(protein_entity_df_assembly.protein_entity_id.unique())].copy()
    assert(len(protein_seq_sites.loc[protein_seq_sites.seq_id == "."]) == 0) #need to have a seq id to map to
    protein_seq_sites["seq_id"] = protein_seq_sites["seq_id"].astype("int")
    protein_seq_sites["auth_seq_id_combined"] = protein_seq_sites["auth_seq_id"].astype("str") + "_" + protein_seq_sites["pdb_ins_code"]
    protein_seq_sites["auth_seq_id_combined"] = protein_seq_sites["auth_seq_id_combined"].str.strip().str.rstrip("?._") 
    protein_entity_df_assembly_domain["auth_seq_range"] = protein_entity_df_assembly_domain.apply(lambda x: protein_seq_sites.loc[(protein_seq_sites.protein_entity_id == x.protein_entity_id) & (protein_seq_sites.seq_id.isin(x.seq_range_chain)), 'auth_seq_id_combined'].values.tolist(), axis = 1)

    #load the contacts data
    contacts = pd.read_json(args.contacts)
    if len(contacts) == 0:
        #for example, only proximal contacts - see 1a1q
        print(f"No contacts found for {args.pdb_id} between ligand and protein entity")
        sys.exit(124)
    contacts_filtered = contacts.loc[(contacts['contact'].apply(lambda x: any(contact_type not in {"proximal", "vdw_clash", "clash"} for contact_type in x))) & (contacts.interacting_entities == "INTER")].copy() #we use inter here becasue we specifically dont want matches to any other selections in the query e.g sugar contacts - only those to non selected positions
    if len(contacts_filtered) == 0:
        #for example, only proximal contacts - see 1a1q
        print(f"No valid contacts found for {args.pdb_id} between ligand and protein entity")
        sys.exit(124)
    contacts_filtered[["bgn_contact", "bgn_auth_asym_id", "bgn_auth_seq_id"]] = contacts_filtered.apply(lambda x: [f"/{x['bgn'].get('auth_asym_id')}/{str(x['bgn'].get('auth_seq_id'))}{str(x['bgn'].get('pdbx_PDB_ins_code')) if str(x['bgn'].get('pdbx_PDB_ins_code')) not in [' ', '.', '?'] else ''}/", x['bgn'].get('auth_asym_id'), f"{x['bgn'].get('auth_seq_id')}_{x['bgn'].get('pdbx_PDB_ins_code')}"], axis = 1, result_type = "expand")
    contacts_filtered[["end_contact", "end_auth_asym_id", "end_auth_seq_id"]] = contacts_filtered.apply(lambda x: [f"/{x['end'].get('auth_asym_id')}/{str(x['end'].get('auth_seq_id'))}{str(x['end'].get('pdbx_PDB_ins_code')) if str(x['end'].get('pdbx_PDB_ins_code')) not in [' ', '.', '?'] else ''}/", x['end'].get('auth_asym_id'), f"{x['end'].get('auth_seq_id')}_{x['end'].get('pdbx_PDB_ins_code')}"], axis = 1, result_type = "expand")
    contacts_filtered["bgn_auth_seq_id"] = contacts_filtered["bgn_auth_seq_id"].str.strip().str.rstrip("?._")
    contacts_filtered["end_auth_seq_id"] = contacts_filtered["end_auth_seq_id"].str.strip().str.rstrip("?._")

    contacts_filtered.loc[~contacts_filtered['bgn_contact'].isin(bound_entity_info_grouped_residue_list), ["bgn_contact", "bgn_auth_asym_id", "bgn_auth_seq_id", 'bgn', "end_contact", "end_auth_asym_id", "end_auth_seq_id", 'end']] = contacts_filtered.loc[
        ~contacts_filtered['bgn_contact'].isin(bound_entity_info_grouped_residue_list), ["end_contact", "end_auth_asym_id", "end_auth_seq_id", 'end', "bgn_contact", "bgn_auth_asym_id", "bgn_auth_seq_id", 'bgn']].values

    contacts_filtered["contact"] = contacts_filtered["contact"].apply(lambda x: [contact for contact in x if contact not in ["proximal", "vdw_clash", "clash"]])
    contacts_filtered["contact_counts"] = contacts_filtered["contact"].str.len()
    contacts_filtered["hbond_counts"] = contacts_filtered["contact"].apply(lambda x: len([contact for contact in x if contact == "hbond"]))
    contacts_filtered["covalent_counts"] = contacts_filtered["contact"].apply(lambda x: len([contact for contact in x if contact == "covalent"]))
    contacts_filtered_filtered = contacts_filtered.drop(columns = ["bgn", "end", "contact", "distance", "interacting_entities", "type"])
    contacts_poly_merged = contacts_filtered_filtered.merge(protein_entity_df_assembly_domain, left_on = "end_auth_asym_id", right_on = "assembly_chain_id_protein", how = "inner")
    if len(contacts_poly_merged) == 0:
        #for example, ligand interacts with DNA only in structure - see 2fjx
        print(f"No contacts found for {args.pdb_id} between ligand and protein entity")
        sys.exit(124)

    contacts_poly_merged["domain_accession"] = contacts_poly_merged["assembly_chain_id_protein"] + ":" + contacts_poly_merged["xref_db_acc"] #db accession is specifc to the symmetry also.
    contacts_poly_merged_filtered = contacts_poly_merged.loc[contacts_poly_merged.apply(lambda x: x.end_auth_seq_id in x.auth_seq_range, axis = 1)].copy()
    if len(contacts_poly_merged_filtered) == 0:
        #for example - see 1y82
        print(f"No contacts found for {args.pdb_id} between ligand and any domains in annotation")
        sys.exit(125)
    contacts_poly_merged_filtered["seq_range_chain"] = contacts_poly_merged_filtered["seq_range_chain"].apply(lambda x: "|".join([str(y) for y in x]))
    contacts_poly_merged_filtered["auth_seq_range"] = contacts_poly_merged_filtered["auth_seq_range"].apply(lambda x: "|".join([str(y) for y in x]))
    contacts_poly_merged_filtered_grouped = contacts_poly_merged_filtered.groupby([col for col in contacts_poly_merged_filtered.columns if col not in ["contact_counts", "hbond_counts", "covalent_counts", "end_auth_seq_id"]]).agg({"contact_counts": "sum", "hbond_counts": "sum", "covalent_counts": "sum", "end_auth_seq_id": set}).reset_index()
    contacts_poly_merged_filtered_grouped.rename(columns = {"contact_counts": "domain_contact_counts", "hbond_counts": "domain_hbond_counts", "covalent_counts": "domain_covalent_counts"}, inplace = True)
    #at this point we may be able to integrate some grouping on identical symmetries?

    bound_entity_info_arp_exploded = bound_entity_info_grouped.explode("arpeggio")
    bound_entity_info_arp_exploded_merged = bound_entity_info_arp_exploded.merge(contacts_poly_merged_filtered_grouped, left_on = "arpeggio", right_on = "bgn_contact", how = "inner")

    bound_entity_info_arp_exploded_merged["end_auth_seq_id"] = bound_entity_info_arp_exploded_merged["end_auth_seq_id"].apply(lambda x: "|".join(str(y) for y in x))
    bound_entity_info_arp_exploded_merged["bgn_auth_seq_id"] = bound_entity_info_arp_exploded_merged["bgn_auth_seq_id"].astype("str")
    bound_entity_info_arp_exploded_merged = bound_entity_info_arp_exploded_merged.assign(**pdb_info_series)
    bound_entity_info_arp_exploded_merged.rename(columns = {"end_auth_seq_id": "domain_residue_interactions", "bgn_auth_seq_id": "bound_ligand_residue_interactions"}, inplace = True)

    bound_entity_info_arp_exploded_merged_aggregated = bound_entity_info_arp_exploded_merged.groupby(["pdb_id", "pdb_descriptor", "pdb_title", "pdb_keywords", "uniqueID", "xref_db", "xref_db_acc", "xref_db_version", "domain_accession", "domain_type", "descriptor", "description", "hetCode", "type", "bound_ligand_struct_asym_id", "ligand_entity_id_numerical", "bound_entity_pdb_residues", "assembly_chain_id_ligand", "assembly_chain_id_protein", "bound_molecule_display_id", "proteinStructAsymID", "auth_chain_id"], dropna=False).agg(
            {"bound_ligand_residue_interactions": set, "domain_residue_interactions": set, "domain_contact_counts": "sum", "domain_hbond_counts": "sum", "domain_covalent_counts": "sum"}).reset_index()

    bound_entity_info_arp_exploded_merged_aggregated = bound_entity_info_arp_exploded_merged_aggregated.loc[bound_entity_info_arp_exploded_merged_aggregated.domain_contact_counts >= args.domain_contact_cutoff]
    if len(bound_entity_info_arp_exploded_merged_aggregated) == 0:
        #if no domain interactions above the cutoff are found e.g. 5i63
        print(f"No domains found for any protein entities in the assembly for {args.pdb_id} with at least {args.domain_contact_cutoff} contacts")
        sys.exit(127)

    bound_entity_info_arp_exploded_merged_aggregated["total_contact_counts"] = bound_entity_info_arp_exploded_merged_aggregated.groupby(["uniqueID", "xref_db"])["domain_contact_counts"].transform("sum")
    bound_entity_info_arp_exploded_merged_aggregated["domain_contact_perc"] = bound_entity_info_arp_exploded_merged_aggregated["domain_contact_counts"] / bound_entity_info_arp_exploded_merged_aggregated["total_contact_counts"]
    bound_entity_info_arp_exploded_merged_aggregated["domain_hbond_perc"] = bound_entity_info_arp_exploded_merged_aggregated["domain_hbond_counts"] / bound_entity_info_arp_exploded_merged_aggregated["total_contact_counts"]
    bound_entity_info_arp_exploded_merged_aggregated["domain_covalent_perc"] = bound_entity_info_arp_exploded_merged_aggregated["domain_covalent_counts"] / bound_entity_info_arp_exploded_merged_aggregated["total_contact_counts"]
    bound_entity_info_arp_exploded_merged_aggregated["num_non_minor_domains"] = bound_entity_info_arp_exploded_merged_aggregated.groupby(["uniqueID", "xref_db"])["domain_contact_perc"].transform(lambda x: len(x[x > 0.1]))
    bound_entity_info_arp_exploded_merged_aggregated = assign_ownership_percentile_categories(bound_entity_info_arp_exploded_merged_aggregated, unique_id = "uniqueID", domain_grouping_key = "domain_accession", database_type = "xref_db", preassigned = True)

    bound_entity_info_arp_exploded_merged_aggregated["domain_residue_interactions"] = \
        bound_entity_info_arp_exploded_merged_aggregated["domain_residue_interactions"].apply(sort_numeric_with_inscode)

    bound_entity_info_arp_exploded_merged_aggregated["bound_ligand_residue_interactions"] = \
        bound_entity_info_arp_exploded_merged_aggregated["bound_ligand_residue_interactions"].apply(sort_numeric_with_inscode)
    #need to work out a logical agg pattern or new unique id system - to deal with domains having different agg patterns
    #for now our agg will just be a copy of the previous
    #bound_entity_info_arp_exploded_merged_aggregated_sym_agg = bound_entity_info_arp_exploded_merged_aggregated.groupby([col for col in bound_entity_info_arp_exploded_merged_aggregated.columns if col not in ["domain_accession", "assembly_chain_id_ligand", "assembly_chain_id_protein", "bound_molecule_display_id", "uniqueID"]], dropna = False).agg({"domain_accession": "first","assembly_chain_id_ligand": "first", "assembly_chain_id_protein": "first", "bound_molecule_display_id": "first", "uniqueID": list}).reset_index()
    #bound_entity_info_arp_exploded_merged_aggregated_sym_agg["represents"] = bound_entity_info_arp_exploded_merged_aggregated_sym_agg["uniqueID"].str.join("|")
    #bound_entity_info_arp_exploded_merged_aggregated_sym_agg["uniqueID"] = bound_entity_info_arp_exploded_merged_aggregated_sym_agg["uniqueID"].apply(lambda x: x[0]) 
    bound_entity_info_arp_exploded_merged_aggregated_sym_agg = bound_entity_info_arp_exploded_merged_aggregated.copy()
    bound_entity_info_arp_exploded_merged_aggregated_sym_agg.to_csv(f"{args.pdb_id}_bound_entity_contacts.tsv", sep = "\t", index = False)

if __name__ == "__main__":
    main()


##extract the symmetry info
##filter to get assembly id 1
## join the ssymetry info to the ligands where necessary 

#split to sym col in contacts ???