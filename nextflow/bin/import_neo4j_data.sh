#!/bin/bash

bin/neo4j-admin database import full \
--array-delimiter="|" \
--skip-bad-relationships \
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
--nodes=pfamDomain=import/pfam_domains_nodes.csv.gz \
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
--nodes=cathHomologousSuperfamily=import/cath_homologous_superfamily_nodes.csv.gz \
--relationships=IS_IN_CATH_HOMOLOGOUS_SUPERFAMILY=import/cath_homologous_superfamily_domain_rels.csv.gz \
--nodes=pfamClan=import/pfam_clans.csv.gz \
--relationships=IS_IN_PFAM_CLAN=import/pfam_clan_rels.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/scop_domain_ligand_interactions.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/cath_domain_ligand_interactions.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/interpro_domain_ligand_interactions.csv.gz \
--relationships=INTERACTS_WITH_LIGAND=import/pfam_domain_ligand_interactions.csv.gz \
--nodes=entry=import/pdb_entry_nodes.csv.gz \
--relationships=IS_IN_PDB=import/be_pdb_rels.csv.gz \
--relationships=IS_IN_PDB=import/cath_pdb_rels.csv.gz \
--relationships=IS_IN_PDB=import/scop_pdb_rels.csv.gz \
--relationships=IS_IN_PDB=import/pfam_pdb_rels.csv.gz \
--relationships=IS_IN_PDB=import/interpro_pdb_rels.csv.gz \
--relationships=IS_IN_EC=import/pdb_ec_rels.csv.gz \
--nodes=procoggraph=import/procoggraph_node.csv.gz \
--overwrite-destination graph.db ; \
bin/neo4j stop; \
bin/neo4j start

