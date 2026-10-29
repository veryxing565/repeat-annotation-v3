# Third-party notices

The workflow's original orchestration and helper code is distributed under
the root MIT license. This does not relicense external tools or their models.

## Included source code

| Directory | Upstream | Base version | License |
| --- | --- | --- | --- |
| `patched_tools/LTR_FINDER_parallel` | https://github.com/oushujun/LTR_FINDER_parallel | 1.4, locally modified | MIT; copyright 2019 Shujun Ou and Ning Jiang |
| `patched_tools/LTR_HARVEST_parallel` | https://github.com/oushujun/LTR_HARVEST_parallel | 1.3, locally modified | MIT; copyright 2019 Shujun Ou and Ning Jiang |

Each directory retains the upstream LICENSE. LTR_HARVEST_parallel is derived
from LTR_FINDER_parallel and its upstream repository is a fork of wild-joker's
work. Only the wrappers and required Perl text helpers are included. No
compiled LTR_FINDER binary, GenomeTools binary, or entire EDTA distribution
is bundled. See [patch notes](docs/LTR_PATCHES.md).

## External dependencies (not distributed here)

- [LTR_retriever](https://github.com/oushujun/LTR_retriever): GPL-3.0.
- [RepeatModeler](https://github.com/Dfam-consortium/RepeatModeler): OSL-2.1.
- [RepeatMasker](https://github.com/Dfam-consortium/RepeatMasker): OSL-2.1.
- [CD-HIT](https://github.com/weizhongli/cdhit): upstream GPL v2 license.
- [TEclass2](https://github.com/IOB-Muenster/TEclass2): obtain its code and
  pretrained model from the upstream provider and check their terms. We did
  not find an explicit redistribution license in the inspected upstream
  root. We do not distribute or assign a license to its code, models, or image.
- LTR_FINDER, GenomeTools, RMBlast, BLAST+, TRF, RepeatScout, RECON, MAFFT,
  Python/Perl libraries, and optional Apptainer retain their respective terms.

Conda recipes or container metadata are not licenses for every component they
install. Installing dependencies is the user's responsibility. Database/model
redistribution permissions must be checked separately.
