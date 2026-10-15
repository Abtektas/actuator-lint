# SPDX-License-Identifier: BSD-3-Clause
"""The licence and the notices of the tool, so that every copy of the program carries them."""

from __future__ import annotations

from . import __version__

COPYRIGHT = "Copyright (c) 2026, the actuator-lint contributors"

# The same text as the file LICENSE; a test compares them.
LICENSE = """\
BSD 3-Clause License

Copyright (c) 2026, the actuator-lint contributors
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

NO_WARRANTY = (
    'This software is provided "as is", without warranty of any kind. The authors and '
    "contributors accept no liability and no responsibility for any use of it or of its results."
)

ENGINE_NOTICE = (
    "The engine (actuator_lint_engine) is built from the control allocation code of PX4, which is "
    "copyright (c) 2012 - 2023, PX4 Development Team and licensed under the BSD 3-Clause license. An engine "
    "package contains that license text as LICENSE-PX4. This project is not affiliated with or "
    "endorsed by the PX4 project or the Dronecode Foundation."
)

TRADEMARK = (
    "PX4 is a trademark of Dronecode Project, Inc. It is used here only to name the software this tool "
    "works with. All other trademarks are the property of their respective owners."
)


REVIEW_AID = (
    "actuator-lint is a review aid, not an airworthiness approval. A report without findings does "
    "not mean the configuration is safe. Whether and how you use the tool and its results is your "
    "own decision, at your own risk."
)


def version_text() -> str:
    """What --version prints: the version, and the terms in short."""
    return "\n".join(
        [
            f"actuator-lint {__version__}",
            COPYRIGHT,
            'License: BSD-3-Clause. "actuator-lint license" prints the full text.',
            NO_WARRANTY,
            REVIEW_AID,
        ]
    )


def license_text() -> str:
    """What "actuator-lint license" prints."""
    return "\n".join(
        [f"actuator-lint {__version__}", "", LICENSE, ENGINE_NOTICE, TRADEMARK, "", NO_WARRANTY, REVIEW_AID, ""]
    )
