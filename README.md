# ProCogGraph
Graph based ligand-domain interaction database for exploring and mining domain-cognate ligand interactions. Powered by PDBe-graph and Neo4j.

### why represent each bound molecule and its constituent entities?

110l_bm1 shows how the consitituent entities of a bound molecule can have different contact counts to the same domain. 

## To Do

| Task | Status | Priority |
| ---- | ------ | -------- |
| Write pipline to annotated CDS from metagenomic libraries with cognate ligand binding profiles | in progress | 1 |
| Obtain biological ligand names from database source | complete (kegg name for all compound IDs, glycans take the GlyTouCan ID for now) | 2 |
| Find new way to combine duplicate biological ligands from different databases | complete (removed RHEA which is predominantly redundant in the biological ligands file, and use kegg compoun ids to agg) | 3 |
| Add new biological ligands to database | not started | 5 |
| Write script to process PDB files into database | not started | 4 |

## PDBe Graph Data

ProCogGraph utilises PDBe graph data to obtain the following information:

* Protein chains: EC number annotation
* Protein chains: SCOP domain annotation
* Protein chains: CATH domain annotation
* Protein chains: InterPro domain annotation
* Bound Molecules: Component entities

## Biological Ligands

### Sources

In ProCogGraph, we collect biological ligands from a variety of database sources including:

* [PubChem](https://pubchem.ncbi.nlm.nih.gov/)
* [KEGG](https://www.genome.jp/kegg/)
* [ChEBI](https://www.ebi.ac.uk/chebi/)
* [Rhea](https://www.rhea-db.org/) *removed in current version*
* [GlyTouCan](https://glytoucan.org/)

Potential databases which will be included in future versions include:

* [PDB Ligand Expo](https://ligand-expo.rcsb.org/ld-download.html)
* [UniProt](https://www.uniprot.org/)
* [Reactome](https://reactome.org/)
* [MetaCyc](https://metacyc.org/)
* [LIPID MAPS](https://www.lipidmaps.org/)
* [HMDB](http://www.hmdb.ca/)
* [BindingDB](https://www.bindingdb.org/bind/index.jsp)
* [PDB](https://www.rcsb.org/)
* [DrugBank](https://www.drugbank.ca/)
* [ChEMBL](https://www.ebi.ac.uk/chembl/)

### Obtaining Biological Ligands

The biological ligands are obtained from the databases listed above using the following steps:

1. Process the enzyme.data from ExPasY to obtain the up to data EC numbers list.
2. Search for KEGG enzyme record matching EC number. If found, extract the EC substrate codes, EC product codes, EC dbxrefs and reactions IDs.
3. For each reaction ID, search for reaction record and extract the substrate codes and product codes.
4. Combine the compound codes (from EC record and reaction record) to obtain a set of compoound IDs for each EC.
5. Search for compound ID records from KEGG and where possible obtain a SMILES string.
6. Search for compound ID records in ChEBI and obtain SMILES string where possible.
7. Search for compound ID records in PubChem (by CID) and obtain SMILES string where possible.
8. Search for glycan IDs in GlyTouCan and obtain SMILES string where possible.
9. Search for EC records in Rhea and obtain reaction SMILES string where possible. Split into component SMILES strings.
10. Combine into a single biological ligands dataframe.

### Naming Biological Ligands in the ProCogGraph Database

Each biological ligand is assigned a unique identifier in the ProCogGraph database. This identifier is a combination of the database source and the database identifier. For example, the biological ligand with the PubChem CID 2244 is assigned the identifier `PubChem:2244`. Every database contains its own naming scheme for biological ligands and these are retained in the ProCogGraph database. For example, the biological ligand with the KEGG ID C00022 is assigned the identifier `KEGG:C00022`. The biological ligand with the ChEBI ID 15377 is assigned the identifier `ChEBI:15377`. The biological ligand with the Rhea ID 15377 is assigned the identifier `Rhea:15377`. The biological ligand with the GlyTouCan ID G00026MO is assigned the identifier `GlyTouCan:G00026MO`.

## Defining Biological Ligand Similarity

### Existing methods of biological ligand similarity

In PROCOGNATE biological ligand similarity is defined as ... EXPLAIN HERE

Subsequently, the PARITY method was developed in 2018 by the Thornton group. EXPLAIN HERE

### ProCogGraph method of biological ligand similarity

In ProCogGraph, we define biological ligand similarity using the PARITY method. Various cutoffs for biological similarity are defined for this score in the literature: 2018 paper uses 0.7, subsequent 2020 paper uses as low as 0.3.

To determine the appropriate cutoff score for ProCogGraph, a receiver operating characteristic (ROC) curve was generated and the score threshold determined using Youden's J statistic. The ROC curve was generated using the following steps:

1. A manually curated set of "cognate" ligands were identified which were already bound to a PDB protein chain.
2. These were scored against their corresponding cognate ligands using the PARITY score. These constitute the positive examples in the ROC curve.
3. PDB ligands were then randomly matched to biological ligands, and scored using the PARITY score. These constitute the negative examples in the ROC curve.
4. The ROC curve was generated using the scikit-learn python package.
5. The score threshold was determined using Youden's J statistic.

The distribution of positive and negative scores is shown in the histogram below:

![Score Distribution]()

The ROC curve is shown below:

![ROC Curve]()

The score threshold was determined to be 0.55 (Youden's index = 0.92).

Potential other avenues for scoring to be explored: the Tanimoto similarity between the Morgan fingerprints of the ligands.

## Domain Ownership

### Existing methods of domain ownership

In PROCOGNATE domain ownership is defined as ...

domain which is most likely to be responsible for the binding of a given ligand. We define this as the domain which has the highest similarity to the ligand. We define similarity as the Tanimoto similarity between the ligand and the domain's cognate ligands. The cognate ligands are defined as the ligands which are bound by the domain's protein chains. The Tanimoto similarity is calculated using the Morgan fingerprint of the ligand and the Morgan fingerprints of the cognate ligands. The Morgan fingerprints are calculated using the RDKit python package.

### ProCogGraph method of domain ownership

Since the original PROCOGNATE database, several tools have been developed, and are integrated into PDBe-graph, which allow a rich description of contacts - primarily, Arpeggio.

In ProCogGraph, domain contact counts are enumerated based on annotations from Arpeggio in PDBe-graph.

. The domain which has the highest number of contacts with the ligand is defined as the domain which is most likely to be responsible for the binding of the ligand.

## Accessing the Database

The ProCogGraph database is available to access at [ProCogGraph](procoggraph.com)

## Creating the Database from source

The ProCogGraph database is created using Neo4J. The database is created using the following steps:

1. Download the latest version of [Neo4J Desktop](https://neo4j.com/download/)
2. Copy the Neo4j files from the `neo4j` folder into the `import` folder in the Neo4J Database.
3. Run the admin-import tool:
```
bin/neo4j-admin database import full --array-delimiter="|" --skip-bad-relationships \
--delimiter="\t" \
--nodes=boundEntity=import/bound_entities.csv.gz \
--nodes=boundDescriptor=import/bound_descriptors.csv.gz \
--relationships=DESCRIBED_BY=import/be_bd_rels.csv.gz \
--nodes=cognateLigand=import/cognate_ligand_nodes.csv.gz \
--relationships=HAS_SIMILARITY=import/bound_entity_parity_score_rels.csv.gz \
--nodes=ecID=import/ec_id_nodes.csv.gz \
--relationships=IS_IN_EC=import/cognate_ligands_ec.csv.gz \
--nodes=ecClass=import/ec_nodes_class.csv.gz \
--relationships=IS_IN_CLASS=import/ec_class_subclass_rel.csv.gz \
--nodes=ecSubClass=import/ec_nodes_subclass.csv.gz \
--relationships=IS_IN_SUBCLASS=import/ec_subclass_subsubclass_rel.csv.gz \
--nodes=ecSubSubClass=import/ec_nodes_subsubclass.csv.gz \
--relationships=IS_IN_SUBSUBCLASS=import/ec_subsubclass_id_rel.csv.gz \
--nodes=cathDomain=import/cath_domains_nodes.csv.gz \
--nodes=scopDomain=import/scop_domains_nodes.csv.gz \
--nodes=interproDomain=import/interpro_domain_nodes.csv.gz \
--relationships=IS_IN_SCOP_FAMILY=import/scop_domain_family_rels.csv.gz \
--nodes=scopFamily=import/scop_family_nodes.csv.gz \
--relationships=IS_IN_SCOP_SUPERFAMILY=import/scop_family_superfam_rels.csv.gz \
--nodes=scopSuperfamily=import/scop_superfamily_nodes.csv.gz \
--relationships=IS_IN_SCOP_FOLD=import/scop_superfam_fold_rels.csv.gz \
--nodes=scopFold=import/scop_fold_nodes.csv.gz \
--relationships=IS_IN_SCOP_CLASS=import/scop_fold_class_rels.csv.gz \
--nodes=IS_IN_SCOP_CLASS=import/scop_class_nodes.csv.gz \
--nodes=cathClass=import/cath_class_nodes.csv.gz \
--relationships=IS_IN_CATH_CLASS=import/cath_class_architecture_rels.csv.gz \
--nodes=cathArchitecture=import/cath_architecture_nodes.csv.gz \
--relationships=IS_IN_CATH_ARCHITECTURE=import/cath_architecture_topology_rels.csv.gz \
--nodes=cathTopology=import/cath_topology_nodes.csv.gz \
--relationships=IS_IN_CATH_TOPOLOGY=import/cath_topology_homology_rels.csv.gz \
--nodes=cathHomology=import/cath_homology_nodes.csv.gz \
--relationships=IS_IN_CATH_HOMOLOGY=import/cath_homology_domain_rels.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/scop_domain_ligand_interactions.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/cath_domain_ligand_interactions.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/interpro_domain_ligand_interactions.csv.gz \
--nodes=proteinChain=import/pdb_protein_chain_nodes.csv.gz \
--nodes=entry=import/pdb_entry_nodes.csv.gz \
--relationships=IS_IN_PDB=import/be_pdb_rels.csv.gz \
--relationships=IS_IN_PDB=import/pdb_protein_rels.csv.gz \
--relationships=IS_IN_PROTEIN_CHAIN=import/cath_protein_rels.csv.gz \
--relationships=IS_IN_PROTEIN_CHAIN=import/scop_protein_rels.csv.gz \
--relationships=IS_IN_PROTEIN_CHAIN=import/interpro_protein_rels.csv.gz \
--relationships=IS_IN_EC=import/protein_ec_rels.csv.gz \
--overwrite-destination neo4j
```
This creates the database.

4. The database can then be started and accessed using the Neo4J Desktop application.

## Database Schema

## Citations

``` python

python3 preprocess_rhea.py --rhea_ec_mapping biological_ligands/data_files/rhea2ec.tsv --rhea_reaction_directions biological_ligands/data_files/rhea-directions.tsv --rd_dir rd/ --outdir . --chebi_names biological_ligands/data_files/chebi_names.tsv.gz

python3 extract_pdbe_info.py --neo4j_user neo4j --neo4j_password 'yTJutYQ$$d%!9h' --outdir pdbe_graph_info2 --enzyme_dat_file ../biological_ligands/enzyme.dat --pdbe_graph_yaml pdbe_graph_queries.yaml --glycoct_cache pdbe_graph_info2/glycoct_cache.pkl --smiles_cache pdbe_graph_info2/smiles_cache.pkl --csdb_linear_cache pdbe_graph_info2/csdb_linear_cache.pkl

python3 get_ec_information.py --ec_dat enzyme.dat --pubchem pubchem_substance_id_mapping.txt --chebi ChEBI_Results.tsv --rhea_mapping rhea-directions.tsv --rhea_reactions rhea-reaction-smiles.tsv --rhea2ec rhea2ec.tsv --outdir biological_ligands

python3 snakemake_ligands_df.py --pdb_ligands_file /raid/MattC/repos/CognateLigandProject/pdbe_graph_files/pdbe_graph_info2/bound_entities_to_score.pkl --cognate_ligands /raid/MattC/repos/CognateLigandProject/biological_ligands/outdir_update/biological_ligands_df.pkl --outdir bound_entities_parity_rhea2 --chunk_size 10 --threads 75 --snakefile parity.smk

python3 assign_domain_ownership.py --cath_bl_residue_interactions_file ../pdbe_graph_files/pdbe_graph_info2/cath_pdb_residue_interactions_distinct_bl_ec.csv.gz --cath_sugar_residue_interactions_file ../pdbe_graph_files/pdbe_graph_info2/cath_pdb_residue_interactions_distinct_sugar_ec.csv.gz  --scop_bl_residue_interactions_file ../pdbe_graph_files/pdbe_graph_info2/scop_pdb_residue_interactions_distinct_bl_ec.csv.gz --scop_sugar_residue_interactions_file ../pdbe_graph_files/pdbe_graph_info2/scop_pdb_residue_interactions_distinct_sugar_ec.csv.gz --interpro_bl_residue_interactions_file ../pdbe_graph_files/pdbe_graph_info2/interpro_pdb_residue_interactions_distinct_bl_ec.csv.gz --interpro_sugar_residue_interactions_file ../pdbe_graph_files/pdbe_graph_info2/interpro_pdb_residue_interactions_distinct_sugar_ec.csv.gz --outdir domain_ownership100 --scop_domains_info_file dir.cla.scop.1_75.txt --scop_descriptions_file dir.des.scop.1_75.txt

python3 produce_neo4j_files.py --enzyme_dat_file ../biological_ligands/enzyme.dat --enzyme_class_file ../biological_ligands/enzclass.txt --outdir neo4j_files_out --biological_ligands ../biological_ligands/outdir_update/biological_ligands_df.pkl --cath_domain_ownership ../domain_ownership/domain_ownership100/cath_combined_domain_ownership.csv --scop_domain_ownership ../domain_ownership/domain_ownership100/scop_combined_domain_ownership.csv --interpro_domain_ownership ../domain_ownership/domain_ownership100/interpro_combined_domain_ownership.csv --bound_ligand_descriptors ../pdbe_graph_files/pdbe_graph_info2/bound_ligands_to_score.pkl --bound_molecules_sugars_smiles ../pdbe_graph_files/pdbe_graph_info2/bound_molecules_sugars_smiles.pkl --parity_calcs ../parity_calcs/bound_entities_parity_rhea2/all_parity_calcs.pkl --interpro_xml ../interpro.xml.gz
```