# Distribution scope

## Included

- SWAT+ source modifications and the corresponding patch.
- Algorithm descriptions, input roles, build instructions and reference Python scripts.
- Existing software authorship and license information.

## Excluded

- Observed discharge, station meteorology and other measured series.
- DEM, land-use and soil layers, pond inventories and GIS/project databases.
- Spatial membership tables, object-specific capacities, allocation quotas and calibrated input tables.
- Complete TxtInOut projects, scenario packages, simulation outputs and result datasets.
- Compiled executables and local backups.

Method coefficients and constants already embedded in source code remain visible. They describe the implementation and do not provide the catchment modelling dataset.

This distribution does not promise data access upon request or permission to redistribute third-party data. Access to any study data requires a separate arrangement with the relevant rights holder.

## Validation and history

The methods-only update preserves the Fortran source and patch. It changes documentation, removes configuration data from the current tree and replaces two machine-specific script paths with environment-configurable paths. Full-model execution and independent reproduction of paper results have not been performed for this update.

Removing files in a new commit does not erase older Git commits, release assets or forks. Earlier commits in an existing repository may still contain configuration tables. The separately prepared methods-only ZIP excludes Git history and local backups; it does not change the history or visibility of a remote repository.
