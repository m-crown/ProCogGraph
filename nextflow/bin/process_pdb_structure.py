#!/usr/bin/env python

from gemmi import cif
import pandas as pd
import argparse
from pathlib import Path

def main():
    ##pre arpeggio run this part:

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--cif', type=str, help='cif file containing PDBe updated structure, may be gzipped')
    parser.add_argument('--pdb_id', type=str, help='pdb id of the structure')
    args = parser.parse_args()


    doc = cif.read(args.cif)
    block = doc.sole_block()

    entity_info = pd.DataFrame(block.find(['_entity.id', '_entity.pdbx_description']), columns = ["entity_id", "description"])
    entity_info["description"] = entity_info["description"].str.strip("\"|'")
    ##see this webinar for details https://pdbeurope.github.io/api-webinars/webinars/web5/arpeggio.html
    assembly_info = pd.DataFrame(block.find(['_pdbx_struct_assembly_gen.assembly_id', '_pdbx_struct_assembly_gen.oper_expression', '_pdbx_struct_assembly_gen.asym_id_list']), columns = ["assembly_id", "oper_expression", "asym_id_list"])
    assembly_info.loc[assembly_info.assembly_id == 1]
    assembly_info["oper_expression"] = assembly_info["oper_expression"].str.split(",")
    assembly_info["asym_id_list"] = assembly_info["asym_id_list"].str.split(",") #asym id here is the struct
    assembly_info_exploded = assembly_info.explode("oper_expression").explode("asym_id_list").rename(columns = {"asym_id_list": "struct_asym_id"})


    branched_seq_info = pd.DataFrame(block.find(['_pdbx_branch_scheme.pdb_asym_id', '_pdbx_branch_scheme.mon_id', '_pdbx_branch_scheme.entity_id', '_pdbx_branch_scheme.pdb_seq_num', '_pdbx_branch_scheme.auth_asym_id', '_pdbx_branch_scheme.auth_seq_num']), columns = ["bound_ligand_struct_asym_id", "hetCode", "entity_id", "pdb_seq_num", "auth_asym_id", "auth_seq_num"])
    branched_seq_info_merged =  pd.DataFrame([], columns = ['bound_ligand_struct_asym_id', 'hetCode', 'entity_id', 'pdb_seq_num', 'auth_asym_id', 'auth_seq_num', 'descriptor'])
    if len(branched_seq_info) > 0:
        branched_seq_info["hetCode"] = "SUGAR"
        branched_sugar_info = pd.DataFrame(block.find(['_pdbx_entity_branch_descriptor.entity_id', '_pdbx_entity_branch_descriptor.descriptor', '_pdbx_entity_branch_descriptor.type']), columns = ["entity_id", "descriptor", "type"])
        branched_sugar_info_wurcs = branched_sugar_info.loc[branched_sugar_info.type == "WURCS"].groupby("entity_id").first()
        branched_sugar_info_wurcs["descriptor"] = branched_sugar_info_wurcs["descriptor"].str.strip("\"|'")
        branched_seq_info_merged = branched_seq_info.merge(branched_sugar_info_wurcs, on = "entity_id", indicator = True)
        assert(len(branched_seq_info_merged.loc[branched_seq_info_merged._merge != "both"]) == 0)
        branched_seq_info_merged.drop(columns = ["_merge", "type"], inplace = True)
        branched_seq_info_merged["type"] = "sugar"

    nonpoly_info = pd.DataFrame(block.find(['_pdbx_entity_nonpoly.entity_id', '_pdbx_entity_nonpoly.comp_id']), columns = ["entity_id", "hetCode"])
    nonpoly_info = nonpoly_info.loc[nonpoly_info.hetCode.isin(["HOH", "UNL"]) == False]
    nonpoly_seq_info_filtered = pd.DataFrame([], columns = ['bound_ligand_struct_asym_id', 'entity_id', 'pdb_seq_num', 'auth_asym_id', 'auth_seq_num', 'hetCode'])
    if len(nonpoly_info) > 0:
        nonpoly_seq_info = pd.DataFrame(block.find(['_pdbx_nonpoly_scheme.asym_id', '_pdbx_nonpoly_scheme.entity_id', '_pdbx_nonpoly_scheme.pdb_seq_num', '_pdbx_nonpoly_scheme.pdb_strand_id', '_pdbx_nonpoly_scheme.auth_seq_num', '_pdbx_nonpoly_scheme.pdb_ins_code']), columns = ["bound_ligand_struct_asym_id","entity_id", "pdb_seq_num", "auth_asym_id", "auth_seq_num", "pdb_ins_code"])
        nonpoly_seq_info_merged = nonpoly_seq_info.merge(nonpoly_info, on = "entity_id", indicator = True)
        assert(len(nonpoly_seq_info_merged.loc[nonpoly_seq_info_merged._merge != "both"])  == 0)
        nonpoly_seq_info_merged.drop(columns = "_merge", inplace = True)
        nonpoly_seq_info_filtered = nonpoly_seq_info_merged.loc[nonpoly_seq_info_merged.hetCode.isin(["HOH", "UNL"]) == False]
        nonpoly_seq_info_filtered["type"] = "ligand"

    if len(branched_seq_info) > 0 or len(nonpoly_info) > 0:
        bound_entity_info = pd.concat([branched_seq_info_merged, nonpoly_seq_info_filtered])
        bound_entity_info = bound_entity_info.merge(entity_info, on = "entity_id", how = "left")
        bound_entity_info["pdb_ins_code"] = bound_entity_info["pdb_ins_code"].fillna("").str.replace("\?|\.", "",regex = True)
        bound_entity_info_assembly = bound_entity_info.merge(assembly_info_exploded, left_on = "bound_ligand_struct_asym_id", right_on = "struct_asym_id", how = "left", indicator = True)
        assert(len(bound_entity_info_assembly.loc[bound_entity_info_assembly._merge != "both"]) == 0)
        bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "ligand") & (bound_entity_info_assembly["oper_expression"].astype("int") > 1), "assembly_chain_id_ligand"] = bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "ligand") & (bound_entity_info_assembly["oper_expression"].astype("int") > 1) , "auth_asym_id"] + "_" + bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "ligand") & (bound_entity_info_assembly["oper_expression"].astype("int") > 1), "oper_expression"].astype("str") 
        bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "sugar") & (bound_entity_info_assembly["oper_expression"].astype("int") > 1), "assembly_chain_id_ligand"] = bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "sugar") & (bound_entity_info_assembly["oper_expression"].astype("int") > 1), "bound_ligand_struct_asym_id"] + "_" + bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "sugar") & (bound_entity_info_assembly["oper_expression"].astype("int") > 1), "oper_expression"].astype("str") 
        bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "ligand"), "assembly_chain_id_ligand"] = bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "ligand"), "assembly_chain_id_ligand"].fillna(bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "ligand"), "auth_asym_id"])
        bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "sugar"), "assembly_chain_id_ligand"] = bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "sugar"), "assembly_chain_id_ligand"].fillna(bound_entity_info_assembly.loc[(bound_entity_info_assembly.type == "sugar"), "bound_ligand_struct_asym_id"])
        bound_entity_info_assembly.drop(columns = ["_merge", "struct_asym_id", "oper_expression"], inplace = True)

        bound_entity_info_grouped = bound_entity_info_assembly.groupby(["bound_ligand_struct_asym_id", "assembly_chain_id_ligand", "entity_id"]).agg({"pdb_ins_code": "first", "hetCode": "first", "descriptor": "first", "description": "first", "type": "first", "auth_seq_num": list, "pdb_seq_num": list}).reset_index()
        bound_entity_info_grouped["bound_molecule_display_id"] = bound_entity_info_grouped.groupby(["assembly_chain_id_ligand", "entity_id"]).ngroup().transform(lambda x: "bm"+ str(x+1)) #we could sort here to try and put bm of identical entities together ? or actually we may want to not sort the groupby as it already is
        bound_entity_info_grouped["uniqueID"] = args.pdb_id + "_" + bound_entity_info_grouped["bound_molecule_display_id"] + "_" + bound_entity_info_grouped["bound_ligand_struct_asym_id"]
        bound_entity_info_grouped.loc[bound_entity_info_grouped.type == "ligand", "arpeggio"] = bound_entity_info_grouped.loc[bound_entity_info_grouped.type == "ligand"].apply(lambda x: [f"/{x['assembly_chain_id_ligand']}/{y}{x['pdb_ins_code']}/" for y in x["pdb_seq_num"]], axis = 1)
        bound_entity_info_grouped.loc[bound_entity_info_grouped.type == "sugar", "arpeggio"] = bound_entity_info_grouped.loc[bound_entity_info_grouped.type == "sugar"].apply(lambda x: [f"/{x['assembly_chain_id_ligand']}/{y}/" for y in x["pdb_seq_num"]], axis = 1)
        bound_entity_info_grouped["bound_entity_auth_residues"] = bound_entity_info_grouped["auth_seq_num"].str.join("|")
        bound_entity_info_grouped["pdb_seq_num"] = bound_entity_info_grouped["pdb_seq_num"].str.join("|")
        bound_entity_info_grouped["entity_id"] = bound_entity_info_grouped["entity_id"].astype(int)
        bound_entity_info_grouped.rename(columns = {"pdb_seq_num" : "bound_entity_pdb_residues", "entity_id": "ligand_entity_id_numerical"}, inplace = True)
        bound_entity_info_grouped["arpeggio"].explode().to_csv(f"{args.pdb_id}_arpeggio.csv", index = False, header = None)
        bound_entity_info_grouped.to_pickle(f"{args.pdb_id}_bound_entity_info.pkl")

if __name__ == "__main__":
    main()