# Ananya RC1 3D model

`ananya-mpfb-cc0.glb` is derived from `avatars/mpfb.glb` in the
[TalkingHead repository](https://github.com/met4citizen/TalkingHead/tree/eed58d198076a7e1e825f804802921c4d3804d46/avatars).
The upstream project identifies that MPFB avatar as
[CC0](https://creativecommons.org/publicdomain/zero/1.0/).

- Upstream revision: `eed58d198076a7e1e825f804802921c4d3804d46`
- Upstream file SHA-256: `63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c`
- SpeakMate optimized file SHA-256: `55b9a25102e435533489c168549c1d5035e6a8c7ba827651da1b7895ec8af0c5`

For the learner web runtime, the source model's non-face textures were capped
at 1024 px and its geometry was compressed with Meshoptimizer. The face texture,
rig, skinning, ARKit expression targets, and Oculus viseme targets were retained.
SpeakMate drives the mouth from measured audio amplitude when provider visemes
are unavailable.
