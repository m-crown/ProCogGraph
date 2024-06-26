## Snakemake - ProCogGraph Database Pipeline ##
##
## @m-crown
##

import time
timestr = time.strftime("%Y%m%d")
output_dir = config["output_dir"] + "_" + timestr

rule all:
    input:
        procoggraph_node = output_dir + "/procoggraph_files/procoggraph_node.csv.gz"

rule produce_neo4j_files:
    input:
        enzyme_dat_file = config["data_files_dir"] + config["enzyme_dat_file"],
        enzyme_class_file = config["data_files_dir"] + config["enzyme_class_file"],
        cognate_ligands = output_dir + "/cognate_ligands/biological_ligands_df.pkl",
        cath_domain_ownership = output_dir + "/pdbe_graph_data/cath_pdb_residue_interactions.csv.gz",
        scop_domain_ownership = output_dir + "/pdbe_graph_data/scop_pdb_residue_interactions.csv.gz",
        interpro_domain_ownership = output_dir + "/pdbe_graph_data/interpro_pdb_residue_interactions.csv.gz",
        pfam_domain_ownership = output_dir + "/pdbe_graph_data/pfam_pdb_residue_interactions.csv.gz",
        bound_ligand_descriptors = output_dir + "/pdbe_graph_data/bound_ligands_to_score.pkl",
        bound_molecules_sugars_smiles = output_dir + "/pdbe_graph_data/bound_molecules_sugars_smiles.pkl",
        parity_calcs = output_dir + "/bound_entities_parity/all_parity_calcs.pkl",
        rhea2ec = config["data_files_dir"] + config["rhea2ec"],
        rhea_directions = config["data_files_dir"] + config["rhea_directions"],
        rhea_reactions_smiles = config["data_files_dir"] + config["rhea_reactions_smiles"],
        script = config["scripts_dir"] + "produce_neo4j_files.py"
    params:
        parity_threshold = config["parity_threshold"],
        outdir = output_dir + "/procoggraph_files"
    output:
        ec_id_nodes = output_dir + "/procoggraph_files/ec_id_nodes.csv.gz",
        ec_nodes_class = output_dir + "/procoggraph_files/ec_nodes_class.csv.gz",
        ec_nodes_subclass = output_dir + "/procoggraph_files/ec_nodes_subclass.csv.gz",
        ec_nodes_subsubclass = output_dir + "/procoggraph_files/ec_nodes_subsubclass.csv.gz",
        ec_class_subclass_rel = output_dir + "/procoggraph_files/ec_class_subclass_rel.csv.gz",
        ec_subclass_subsubclass_rel = output_dir + "/procoggraph_files/ec_subclass_subsubclass_rel.csv.gz",
        ec_subsubclass_id_rel = output_dir + "/procoggraph_files/ec_subsubclass_id_rel.csv.gz",
        cognate_ligand_nodes = output_dir + "/procoggraph_files/cognate_ligand_nodes.csv.gz",
        cognate_ligands_ec = output_dir + "/procoggraph_files/cognate_ligands_ec.csv.gz",
        pdb_nodes = output_dir + "/procoggraph_files/pdb_entry_nodes.csv.gz",
        protein_entities = output_dir + "/procoggraph_files/pdb_protein_chain_nodes.csv.gz",
        protein_ec_rels = output_dir + "/procoggraph_files/protein_ec_rels.csv.gz",
        scop_domains_nodes = output_dir + "/procoggraph_files/scop_domains_nodes.csv.gz",
        cath_domains_nodes = output_dir + "/procoggraph_files/cath_domains_nodes.csv.gz",
        interpro_domains_nodes = output_dir + "/procoggraph_files/interpro_domain_nodes.csv.gz",
        pfam_domains_nodes = output_dir + "/procoggraph_files/pfam_domains_nodes.csv.gz",
        scop_family_nodes = output_dir + "/procoggraph_files/scop_family_nodes.csv.gz",
        scop_superfamily_nodes = output_dir + "/procoggraph_files/scop_superfamily_nodes.csv.gz",
        scop_fold_nodes = output_dir + "/procoggraph_files/scop_fold_nodes.csv.gz",
        scop_class_nodes = output_dir + "/procoggraph_files/scop_class_nodes.csv.gz",
        scop_domain_family_rels = output_dir + "/procoggraph_files/scop_domain_family_rels.csv.gz",
        scop_family_superfamily_rels = output_dir + "/procoggraph_files/scop_family_superfam_rels.csv.gz",
        scop_superfamily_fold_rels = output_dir + "/procoggraph_files/scop_superfam_fold_rels.csv.gz",
        scop_fold_class_rels = output_dir + "/procoggraph_files/scop_fold_class_rels.csv.gz",
        cath_class_nodes = output_dir + "/procoggraph_files/cath_class_nodes.csv.gz",
        cath_architecture_nodes = output_dir + "/procoggraph_files/cath_architecture_nodes.csv.gz",
        cath_topology_nodes = output_dir + "/procoggraph_files/cath_topology_nodes.csv.gz",
        cath_homologous_superfamily_nodes = output_dir + "/procoggraph_files/cath_homologous_superfamily_nodes.csv.gz",
        cath_class_architecture_rels = output_dir + "/procoggraph_files/cath_class_architecture_rels.csv.gz",
        cath_architecture_topology_rels = output_dir + "/procoggraph_files/cath_architecture_topology_rels.csv.gz",
        cath_topology_homologous_superfamily_rels = output_dir + "/procoggraph_files/cath_topology_homology_rels.csv.gz",
        cath_homologous_superfamily_domain_rels = output_dir + "/procoggraph_files/cath_homologous_superfamily_domain_rels.csv.gz",
        pfam_clans = output_dir + "/procoggraph_files/pfam_clans.csv.gz",
        pfam_clan_rels = output_dir + "/procoggraph_files/pfam_clan_rels.csv.gz",
        bound_descriptors = output_dir + "/procoggraph_files/bound_descriptors.csv.gz",
        bound_entities_descriptors = output_dir + "/procoggraph_files/be_bd_rels.csv.gz",
        be_pdb_rels = output_dir + "/procoggraph_files/be_pdb_rels.csv.gz",
        parity_rels = output_dir + "/procoggraph_files/bound_entity_parity_score_rels.csv.gz",
        cath_domain_ligand_interactions = output_dir + "/procoggraph_files/cath_domain_ligand_interactions.csv.gz",
        scop_domain_ligand_interactions = output_dir + "/procoggraph_files/scop_domain_ligand_interactions.csv.gz",
        pfam_domain_ligand_interactions = output_dir + "/procoggraph_files/pfam_domain_ligand_interactions.csv.gz",
        interpro_domain_ligand_interactions = output_dir + "/procoggraph_files/interpro_domain_ligand_interactions.csv.gz",
        pdb_protein_rels = output_dir + "/procoggraph_files/pdb_protein_rels.csv.gz",
        cath_protein_rels = output_dir + "/procoggraph_files/cath_protein_rels.csv.gz",
        scop_protein_rels = output_dir + "/procoggraph_files/scop_protein_rels.csv.gz",
        pfam_protein_rels = output_dir + "/procoggraph_files/pfam_protein_rels.csv.gz",
        interpro_protein_rels = output_dir + "/procoggraph_files/interpro_protein_rels.csv.gz",
        procoggraph_node = output_dir + "/procoggraph_files/procoggraph_node.csv.gz"
    threads: 1
    shell: 
        "python3 {input.script} --enzyme_dat_file {input.enzyme_dat_file} --enzyme_class_file {input.enzyme_class_file} --outdir {params.outdir} --cognate_ligands {input.cognate_ligands} --cath_domain_ownership {input.cath_domain_ownership} --scop_domain_ownership {input.scop_domain_ownership} --interpro_domain_ownership {input.interpro_domain_ownership} --pfam_domain_ownership {input.pfam_domain_ownership} --bound_ligand_descriptors {input.bound_ligand_descriptors} --bound_molecules_sugars_smiles {input.bound_molecules_sugars_smiles} --parity_calcs {input.parity_calcs} --parity_threshold {params.parity_threshold} --rhea2ec {input.rhea2ec} --rhea_dir {input.rhea_directions} --rhea_reaction_smiles {input.rhea_reactions_smiles}"


rule get_pdb_parity:
    input:
        pdb_ligands_to_score = output_dir + "/pdbe_graph_data/bound_entities_to_score.pkl",
        cognate_ligands = output_dir + "/cognate_ligands/biological_ligands_df.pkl",
        script = config["scripts_dir"] + "get_pdb_parity.py",
    params:
        parity_cache = config["cache_files_dir"] + config["parity_cache"],
        threshold = config["parity_threshold"],
        outdir = output_dir + "/bound_entities_parity"
    output:
        parity_calcs = output_dir + "/bound_entities_parity/all_parity_calcs.pkl"
    threads: workflow.cores
    shell:
        "python3 {input.script} --cache {params.parity_cache} --processed_ligands_file {input.pdb_ligands_to_score} --cognate_ligands_file {input.cognate_ligands} --outdir {params.outdir} --threads {threads} --threshold {params.threshold}"

rule cognate_ligands:
    input:
        enzyme_dat_file = config["data_files_dir"] + config["enzyme_dat_file"],
        enzyme_class_file = config["data_files_dir"] + config["enzyme_class_file"],
        pubchem_mapping = config["data_files_dir"] + config["pubchem_mapping"],
        chebi_kegg = config["data_files_dir"] + config["chebi_kegg"],
        chebi_relations = config["data_files_dir"] + config["chebi_relations"],
        rhea_reactions = output_dir + "/cognate_ligands/rhea_reactions.pkl",
        brenda_json = config["data_files_dir"] + config["brenda_json"],
        brenda_ligands = config["data_files_dir"] + config["brenda_ligands"],
        brenda_mol_dir = config["data_files_dir"] + config["brenda_mol_dir"],
        script = config["scripts_dir"] + "get_ec_information.py"
    output:
        cognate_ligands = output_dir + "/cognate_ligands/biological_ligands_df.pkl"
    params:
        kegg_enzyme_cache = config["cache_files_dir"] + config["kegg_enzyme_cache"],
        kegg_reaction_cache = config["cache_files_dir"] + config["kegg_reaction_cache"],
        smiles_cache = config["cache_files_dir"] + config["smiles_cache"],
        csdb_linear_cache = config["cache_files_dir"] + config["csdb_linear_cache"],
        kegg_compound_cache_dir = config["cache_files_dir"] + config["kegg_compound_cache_dir"],
        glytoucan_cache = config["cache_files_dir"] + config["glytoucan_cache"],
        outdir = output_dir + "/cognate_ligands"
    threads: 1
    shell:
        "python3 {input.script} --ec_dat {input.enzyme_dat_file} --enzyme_class_file {input.enzyme_class_file} --pubchem {input.pubchem_mapping} --chebi {input.chebi_kegg} --chebi_relations {input.chebi_relations} --rhea_reactions {input.rhea_reactions} --outdir {params.outdir} --kegg_enzyme_string {params.kegg_enzyme_cache} --kegg_reaction_string {params.kegg_reaction_cache} --smiles_cache {params.smiles_cache} --csdb_cache {params.csdb_linear_cache} --compound_cache_dir {params.kegg_compound_cache_dir} --gtc_cache {params.glytoucan_cache} --brenda_mol_dir {input.brenda_mol_dir} --brenda_json {input.brenda_json} --brenda_ligands {input.brenda_ligands}"

rule preprocess_rhea:
    input:
        rhea2ec = config["data_files_dir"] + config["rhea2ec"],
        rhea_directions = config["data_files_dir"] + config["rhea_directions"],
        rd_dir = config["data_files_dir"] + config["rhea_rd_dir"],
        chebi_names = config["data_files_dir"] + config["chebi_names"],
        script = config["scripts_dir"] + "preprocess_rhea.py"
    output:
        rhea_reactions = output_dir + "/cognate_ligands/rhea_reactions.pkl"
    params:
        outdir = output_dir + "/cognate_ligands"
    threads: 1
    shell:
        "python3 {input.script} --rhea_ec_mapping {input.rhea2ec} --rhea_reaction_directions {input.rhea_directions} --rd_dir {input.rd_dir} --chebi_names {input.chebi_names} --outdir {params.outdir}"

rule get_pdbe_graph_info:
    input:
        pdbe_graph_yaml = config["scripts_dir"] + config["pdbe_graph_yaml"],
        enzyme_dat_file = config["data_files_dir"] + config["enzyme_dat_file"],
        enzyme_class_file = config["data_files_dir"] + config["enzyme_class_file"],
        sifts_ec_mapping = config["data_files_dir"] + config["sifts_ec_mapping"],
        scop_domains_info_file = config["data_files_dir"] + config["scop_domains_info_file"],
        scop_descriptions_file = config["data_files_dir"] + config["scop_descriptions_file"],
        interpro_xml = config["data_files_dir"] + config["interpro_xml"],
        pfam_clans = config["data_files_dir"] + config["pfam_clans"],
        pfam_clan_rels = config["data_files_dir"] + config["pfam_clan_rels"],
        pfam_a_file = config["data_files_dir"] + config["pfam_a_file"],
        cddf = config["data_files_dir"] + config["cddf"],
        script = config["scripts_dir"] + "extract_pdbe_info.py"
    output:
        bound_entities_to_score = output_dir + "/pdbe_graph_data/bound_entities_to_score.pkl",
        cath_pdb_residue_interactions = output_dir + "/pdbe_graph_data/cath_pdb_residue_interactions.csv.gz",
        scop_pdb_residue_interactions = output_dir + "/pdbe_graph_data/scop_pdb_residue_interactions.csv.gz",
        interpro_pdb_residue_interactions = output_dir + "/pdbe_graph_data/interpro_pdb_residue_interactions.csv.gz",
        pfam_pdb_residue_interactions = output_dir + "/pdbe_graph_data/pfam_pdb_residue_interactions.csv.gz",
        bound_ligand_descriptors = output_dir + "/pdbe_graph_data/bound_ligands_to_score.pkl",
        bound_molecules_sugars_smiles = output_dir + "/pdbe_graph_data/bound_molecules_sugars_smiles.pkl"
    params:
        neo4j_user = config["neo4j_user"],
        neo4j_password = config["neo4j_password"],
        neo4j_bolt_uri = config["neo4j_bolt_uri"],
        outdir = output_dir + "/pdbe_graph_data", 
        glycoct_cache = config["cache_files_dir"] + config["glycoct_cache"],
        smiles_cache = config["cache_files_dir"] + config["smiles_cache"],
        csdb_linear_cache = config["cache_files_dir"] + config["csdb_linear_cache"],
        sugar_cifs = config["cache_files_dir"] + config["sugar_cifs_cache_dir"],
        domain_contact_cutoff = config["domain_contact_cutoff"]
    threads: workflow.cores

    shell: 
        "python3 {input.script} --neo4j_user '{params.neo4j_user}' --neo4j_password '{params.neo4j_password}' --neo4j_bolt_uri {params.neo4j_bolt_uri} --outdir {params.outdir} --enzyme_dat_file {input.enzyme_dat_file} --enzyme_class_file {input.enzyme_class_file} --pdbe_graph_yaml {input.pdbe_graph_yaml} --glycoct_cache {params.glycoct_cache} --smiles_cache {params.smiles_cache} --csdb_linear_cache {params.csdb_linear_cache} --sifts_ec_mapping {input.sifts_ec_mapping} --cddf {input.cddf} --scop_domains_info_file {input.scop_domains_info_file} --scop_descriptions_file {input.scop_descriptions_file} --interpro_xml {input.interpro_xml} --threads {threads} --pfam_clans {input.pfam_clans} --pfam_clan_rels {input.pfam_clan_rels} --pfam_a_file {input.pfam_a_file} --domain_contact_cutoff {params.domain_contact_cutoff} --pdbecif_dir {params.sugar_cifs}"
