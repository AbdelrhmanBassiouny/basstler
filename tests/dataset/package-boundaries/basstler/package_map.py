"""
The dataset package's map, where a higher distribution lists a lower one.
"""

from __future__ import annotations

from basstler.package_map import (
    Distribution,
    DistributionDeclaration,
    Layer,
    PackageMap,
)

# %% the dataset's map

PACKAGE_MAP = PackageMap(
    (
        DistributionDeclaration(Distribution.CORE, Layer.CORE, ("low",)),
        DistributionDeclaration(
            Distribution.GIT,
            Layer.LOCAL_TOOLS,
            ("high",),
            (Distribution.CORE,),
        ),
    )
)
"""
The lower distribution ships ``low``, and the higher one ``high``.
"""
