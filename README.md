# Feeder-Level PV Capacity Estimation

This repository contains the code and files developed for a research project on estimating behind-the-meter (BTM) photovoltaic (PV) capacity at the distribution-feeder level using aggregated power measurements.

> **Project status:** This project is under active development. The code, documentation, methodology, and experiments are preliminary and may change. The repository will be updated, corrected, and improved as the research progresses.

## Research objective

The project investigates methods for estimating the installed capacity of behind-the-meter PV systems using feeder-level measurements, without requiring direct measurements from each individual PV installation.

## Test distribution network

The study uses a real-world **240-node distribution test system** from the Midwestern United States. The system was described by Bu et al. (2019) in:

> F. Bu, Y. Yuan, Z. Wang, K. Dehghanpour, and A. Kimber, “A Time-series Distribution Test System Based on Real Utility Data,” *2019 North American Power Symposium (NAPS)*, Wichita, KS, USA, 2019, pp. 1–6.  
> Paper: https://arxiv.org/abs/1906.04078  
> DOI: https://doi.org/10.1109/NAPS46351.2019.9000245

The system includes three primary feeders supplied by a substation and represents a real distribution network. The publication describes approximately 23 miles of primary feeder conductors and smart-meter measurements from **1,120 customers**, covering January through December 2017 at hourly resolution. The published dataset includes the distribution-system model and the one-year smart-meter data.

The system description, data, and OpenDSS model are made available by Zhaoyu Wang's research group on the Iowa Distribution Test Systems website:

- **Test-system and data portal:** https://wzy.ece.iastate.edu/testsystem.html

Please consult the original paper and data portal for the authoritative description, data conditions, and citation requirements.

## Purpose of this implementation

The 240-node network was implemented in OpenDSS using the Python engine interface as a test environment for developing and evaluating a model for **behind-the-meter PV capacity disaggregation/estimation at the distribution-feeder level**. The implementation provides a controlled simulation environment in which PV systems can be added to the network under defined scenarios, power-flow simulations can be performed, and the resulting feeder-level measurements can be used to test estimation methods.

The initial research focuses on estimating aggregate installed PV capacity from changes in feeder-level active and reactive power, together with irradiance data. The simulation environment supports experiments with different PV penetration levels, stochastic PV placement, and inverter operating conditions, including unity power factor and Volt-VAr control. These scenarios help evaluate the method under different operating conditions and compare its estimates with known values from the simulated cases.

The test network is intended to be reusable: it can support the evaluation of different disaggregation or estimation methods, and potentially other research questions involving distribution-network behavior and behind-the-meter PV integration.
 

## Planned repository organization

At this stage, the network implementation, model-development code, scripts, data, and experiment outputs are kept in a single repository for convenience. As the work matures, the intention is to separate the project into two repositories:

1. **Distribution test network:** a standalone test environment containing the 240-node network model, supporting configuration and simulation tools, and the resources needed to create and run test scenarios. Its purpose will be to serve as a reusable environment for testing different models and methods addressing different research objectives.
2. **PV capacity estimation model:** a dedicated repository containing the specific estimation method developed in this research, including its implementation, configuration, and evaluation procedures.

This separation is planned rather than completed. The current repository may therefore contain files that will later be reorganized or moved to one of the two repositories.

## Repository contents

The current repository is organized into folders for the main components of the research, including:

- `estimador_PV/` — PV-capacity estimation code.
- `elementos_dss/` — OpenDSS model elements and related files.
- `scripts/` — supporting scripts.
- `dados/` — input data used by the workflow.
- `experimentos/` — experiment configurations and execution-related files.
- `resultados/` — generated results.
- `documentacao/` — project notes and documentation.
- `figuras/` — figures used for analysis or reporting.

The structure and contents may change as the project develops. Not every file or dataset is necessarily intended for public redistribution; check applicable permissions and data licenses before sharing or reusing materials.

## Current status and reproducibility

This repository is a work in progress. Scripts, instructions, and experiment workflows may be incomplete or require local configuration. Results should be interpreted in the context of the current research stage, and should not be treated as a finalized software release.

Further updates are planned to improve the code, documentation, reproducibility, and organization of the experiments.

## Documentation status

The documentation is currently basic and will be expanded and improved in the near future. In the meantime, the scripts include explanatory comments intended to help readers understand their purpose and operation. Some steps may still require familiarity with Python, OpenDSS, and the project structure.

## Author

**Matheus Almeida**  
Electrical Engineer | M.Sc. in Mathematical and Computational Modeling | Ph.D. Student

Email: [matheus.almeida@sou.unijui.edu.br](mailto:matheus.almeida@sou.unijui.edu.br)
