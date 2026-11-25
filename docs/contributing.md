# Contributing

The working agreement (branches, commits, tests and CI) is in `CLAUDE.md` at the
repository root. This page covers what a checkout needs beyond it.

## Git LFS

Downloaded binaries under `game/assets/materials/` and `game/assets/models/` live
in Git LFS ([ADR-022](adr/ADR-022-diorama-presentation.md), decided with #652).
Everything else is ordinary Git, including the textures already under
`game/assets/textures/`. The patterns in `.gitattributes` are path-scoped on
purpose: a repository-wide `*.png` would match those older blobs and leave every
clone showing them as modified.

### Install git-lfs

macOS: `brew install git-lfs`. Debian or Ubuntu: `sudo apt install git-lfs`.
Check with `git lfs version`.

### Set up a clone, once

From the clone's root:

```bash
git lfs install --local --skip-repo
git lfs update --force
poetry run pre-commit install --hook-type pre-push
```

1. The first writes the LFS filters into this repository's `.git/config` only,
   and touches no hook and no working tree.
2. The second installs LFS's `post-checkout`, `post-commit`, `post-merge` and
   `pre-push` hooks.
3. The third hands `pre-push` back to pre-commit, which keeps LFS's hook as
   `pre-push.legacy` and runs it first.

Plain `git lfs install` is not enough here. pre-commit already owns `pre-push`,
so `git lfs install` exits with "Hook already exists: pre-push" and installs no
hook at all. Without LFS's pre-push hook, a push carries the pointers but uploads
no object, and every other checkout then gets pointers.

### Worktrees

Worktrees share the main clone's `.git/config`, its hooks and its LFS store
(`.git/lfs/objects`; `git lfs env` shows the paths). `git worktree add` therefore
checks out the real binaries, fetching a missing object once for every worktree.

### A light clone

`GIT_LFS_SKIP_SMUDGE=1 git clone ...` (or `git worktree add`) checks out
131-byte pointer files instead of the binaries, which is enough for backend
work. `git lfs pull` fetches the binaries later.

### Pointer files

A pointer is a small text file that begins with
`version https://git-lfs.github.com/spec/v1`. Where a binary is still a pointer:

- Godot logs image-load errors for `game/assets/materials/...`, and the slab's
  extension renders without its textures;
- `game/tests/unit/test_asset_credits.gd` fails with "is a Git LFS pointer: run
  `git lfs pull`".

Fix it with `git lfs pull` (after the setup above, if the filter was missing).
`git lfs fsck --pointers` checks the result. If Godot imported the project while
the binaries were pointers, it marked their `.import` files `valid=false`;
restore them with `git checkout -- game/assets/materials game/assets/models`
and import again (`godot --path game --headless --import`).

### CI

The Godot CI `test` job and Client Smoke check out with `lfs: true`; no other job
loads the assets. Those downloads count against the repository owner's free
10 GiB of LFS bandwidth a month, so each asset PR reports its LFS bytes and the
projected monthly CI download. The PR that takes LFS past about 20 MB at HEAD
proposes an `actions/cache` of `.git/lfs`.

## Downloaded assets

The conventions every asset PR follows (#652, ADR-022 decision 5):

- CC0 sources first, such as Poly Haven and ambientCG. Any other licence needs
  Edwin's approval first.
- Texture sets go in `game/assets/materials/<set>/<set>_diff.jpg`,
  `_nor_gl.jpg` (OpenGL normal map) and `_arm.jpg` (ambient occlusion,
  roughness, metallic).
- 512 px, JPEG quality 90. A set may use 1k only where a frame at orthographic
  size 3.5 or less shows 512 px is not enough, and at most three sets may.
- Commit the `.import` files with `compress/mode=2`, `mipmaps/generate=true`,
  and `compress/normal_map=1` for normal maps.
- `game/assets/CREDITS.md` has one row per file: source URL, author, licence,
  download date and edits. `test_asset_credits.gd` checks that every file loads
  and has its row.
- The PR carries `/visual-check` frames for every scenario it touches.
