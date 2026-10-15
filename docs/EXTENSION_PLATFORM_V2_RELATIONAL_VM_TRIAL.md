# WP4 — controlled relational VM trial, 2026-10-14

Status: live preparation, prepared start, scoped SQL/revoke, controlled restart
and actual Ubuntu/WSL cold-boot gates accepted for this exact fixture.
Not WP4/M20 closure, a production rollout or general relational boot acceptance.

## Exact boundary

The owner's Ubuntu/WSL installation remains `0.3.0-beta.49`, commit
`479b5e6591d8f30ef07231988ec9b5230089d9b1`. `/opt/3mm/current` and the immutable
release were not edited. No new release, helper replacement, credential/key
rotation or business-extension adoption was used. The owner separately authorized
fixture stop/recovery, a new start, boot enabling and a full Ubuntu/WSL restart.

Only the separate headless `org.3mm.wp4-relational-test` 1.0.0 fixture was changed:

- Installation 5, incarnation `3e47f86550ad5361135bdea78a8f20be`.
- Instance `864a83238cf059d40166f2f6`.
- ZIP SHA-256 `e3afeeba492b1eb30351ebbf8229c27fa1337ccd940f575bba9b96f2f09157d0`.
- Schema `0001`, own database 1 MiB; only declared relational read/write scopes.

At the owner's request, unpublished restored-empty recovery/resumption and
witness fixes were exercised through verified, root-owned read-only code
snapshots and restricted one-shot workers. Real Core-UID metadata workers,
existing review key, current administrator authentication and sealed actions
were used; tokens/keys never entered argv, environment overrides or files.
The installed beta.49 Core and non-root application host served all SQL probes.
This is a controlled prototype trial, **not** a public beta.49 recovery recipe.

The final code-only snapshot was
`52ec91f31a24938dc6db05df305d30fc0f3e0e2a3b866cbeecb1c3ea1f85ba21` under
`/var/lib/3mm-wp4-trial`. The first SQL phase used an ephemeral `/run/systemd/system`
drop-in selecting `Type=exec`. For the separately authorized reboot, this fixture
alone received the same protected override at
`/etc/systemd/system/3mm-application-extension@864a83238cf059d40166f2f6.service.d/90-wp4-trial-type-exec.conf`
(root:root, 0644); no existing persistent file was overwritten. That override
remains after reboot. Other instance configurations and the installed template
were not changed. The source template fix and recovery commands still need
normal release verification/publication.

Reviewed-native code remains **not a sandbox**; limits remain cooperative.

## Recovery and two deployment defects

The beta.48 failed migration remains `execution_unconfirmed`, without an invented
completion receipt. Its exact restored-empty checkpoint was reconciled and
archived, retaining the original key, wheel and source history. Separate new
migration consent produced preparation `718b87f2a29f45b7afd276ce608947a9`, durably
`prepared_not_started`, with zero synthetic business records.

The trial then exposed two real deployment differences from isolated root tests:

1. Atomic replacement of a root-only stop witness inherited the helper's primary
   group `3mm` rather than the required `root:root`. The writer now supports
   explicit ownership; start/stop/boot witness updates set UID/GID 0 before
   publishing replacements. Readers retain their strict ownership checks. The
   old incorrectly grouped witness was not edited or deleted; a separate verified
   stop created new valid evidence.
2. `Type=simple` acknowledges fork before credential/namespace setup and exec.
   The immediate kernel-principal check could see the transitional root executor
   and correctly refuse. `Type=exec` removes that premature acknowledgement;
   the verifier still rejects a root/wrong principal. No polling fallback,
   credential-check relaxation or direct `systemctl start` bypass was introduced.

Every refused start kept its original action ID/witness. Fresh reconciliation
verified a stop, followed by separately reviewed resources and a new one-use
reactivation. No uncertain start was retried, nor preparation/migration replayed.

The first successful start `d2c43e3b21c447f7a00206cdb12de001` returned the sealed
`active_review_required` result. Kernel evidence verified UID994/GID985 for all
four real/effective/saved/fs identities, zero effective/ambient capabilities and
`NoNewPrivileges=1`. At that phase the unit was active/running but boot-disabled.
Rights required a fresh post-start review → approve → apply.

## Actual signed SDK SQL acceptance

These probes used normal authenticated Core operations and signed SDK admission:

- Initial read: `missing`, count 0.
- Synthetic write `780d59e7dc12459e876db5c3f75deaca`: `stored`.
- Read and own business-record lookup: found, count 1.
- Same ID/text: `replayed`, still one business record.
- Same ID/changed text: `conflict`, original unchanged.
- `ATTACH ':memory:'` through read access: blocked; succeeding read/count remained
  correct, proving the SQL fence rather than merely absent permission.
- Explicit fixture-only revoke: new read and new write both refused HTTP409.
- Fresh review/approve/apply: original text/digest/count 1 preserved; denied
  request `159c8b63a4844c07b8ef580dc440747f` remained `missing`.

Original synthetic text is `WP4 relational beta49 trial`, SHA-256
`7e6a31df1d9c27d7fe5111d726db982592ef7545207434625a857e897c355a10`.
The record is application deduplication evidence, **not** the private-file
fixture's Core receipt or an exactly-once transport claim. Repeats consume new
admitted SQL transactions, but do not duplicate the business row.

The generic authority status still conservatively reports
`relational_runtime_unavailable` / `grant_effective: false`. Actual current grant
state plus successful signed SQL, not that generic label, is the bounded runtime
proof. No grants were repeatedly reapplied merely to change that label.

## Controlled restart and actual cold-boot acceptance

The owner authorized these separate actions after the SQL/revoke gate. Read-only
checks found no active M21 build/test/development process before the WSL restart.
No migration, additional business write or direct service-start bypass was used.

1. Stop-only recovery `4f1be0733e4a4c97886f4ee292f1e6f8` confirmed
   `stopped_review_required`, revision `57a65ce828d6e6b842becdd4b3429ff2`.
   The prepared database, original transport key and lifecycle were preserved.
2. After separate pre-start review/approve/apply, reactivation
   `957f67f3798c494ca8d18a5b84860904` confirmed `active_review_required`.
   PID changed from 34563 to 35222; boot remained disabled. Separate post-start
   review/approve/apply produced grant revision 11, record
   `9991e193ab672fe9e277c3e72b21f7d3`. Signed SDK reads preserved the original
   text/digest/count 1 and the denied request remained absent.
3. Enable-only boot action `d39c98e2525447e39822876981bbcf27` confirmed
   `boot_enabled_not_started`, revision `23515fc102278f819134b3751cc237e3`.
   The unit became enabled with the same PID 35222; no start, SQL mutation or
   new grant occurred. An expired-login preflight had refused before issuing
   this action; explicit login preceded the single issued boot action.
4. Installed services stopped normally, then `wsl --shutdown` completed.
   The retained cold boot ID is `64e06304-2557-48a2-a747-7c6dbd8ade37`, different
   from pre-reboot `6769211a-cd28-4050-8828-160b41f073a8`. The fixture became
   active/running/enabled automatically, PID 545. No manual start or rights
   approval was sent after boot.

The first short-lived cold probe caught Core before its platform socket was
ready: the application refused before package-factory import. Its existing
systemd restart policy subsequently uses a fresh process/admission, not replay of
an uncertain mutation or a permission fallback. Short-lived WSL clients also let
the instance cycle without an interactive client holding it open; a plain
non-root Ubuntu shell was retained for the final checks. No keepalive daemon,
scheduled task or credentials on disk were introduced.

A read-only worker under the actual installed Core UID verified both the Core
seal and transport HMAC of exactly one admitted startup record for the current
PID/boot, nonce `fca6c68018a64558be777d2f6c6c84b1`. It matches the confirmed boot
setting and unchanged grant revision 11. Kernel evidence again verified UID994
and GID985 for all four identities, zero effective/ambient capabilities and
`NoNewPrivileges=1`. The original transport key is unchanged.

After cold boot, all four Core/Agent/Web/update-helper services are active and
both readiness endpoints pass. Agent identity remains
`dev_ad7e90a045214c4088ed6ed7df50bec2`. Actual signed SDK read returns the original
text/hash and count 1; denied request `159c8b63a4844c07b8ef580dc440747f` is still
`missing`. Installed beta.49 and its release symlink remain unchanged. This is
bounded live prototype evidence with the documented fixture override, not proof
that the unpublished fixes are already present in the immutable release.

## Verification and remaining gates

The wider isolated Linux/root activation, stop recovery, reactivation, boot and
legacy activation regression run passed **280 cases**. The final dedicated
ownership/unit-profile suite passed **6 cases** (five overlap that run); Windows
passed 5 with its one expected Linux-root skip. Formatting, whitespace checks
and `npm run build-only` passed. Existing deprecation/test-key warnings were not
suppressed or addressed as unrelated work. These are targeted checks, not another
full release suite. After recording the restart/boot results, whitespace/link
checks and `npm run build-only` were repeated successfully; the 280-case run was
not repeated for these documentation-only changes.

The normal post-business restart and separately consented WSL cold boot now have
the live evidence above. Genuine interrupted-start fault injection, relational
upgrade/portable restore/rekey, nonempty recovery, general account provisioning
and the broader neutral Standalone/Hub acceptance remain unclaimed. Future
shared VM/WSL restarts still need separate agreement because parallel M21 work may
be running. No business extension may use this trial as generic installation
authority.

The subsequent [source-level boot preservation fence](EXTENSION_PLATFORM_V2_RELATIONAL_BOOT_FENCE.md)
refuses initial preparation/relineage while boot evidence needs separate
reconciliation. Its isolated tests do not modify this accepted live fixture or
turn the trial into upgrade/portable restore acceptance.

See [fixture procedure](../modules/wp4-relational-test/README.md),
[restored-empty recovery](EXTENSION_PLATFORM_V2_RESTORED_EMPTY_RECOVERY.md) and
[WP4 closure audit](EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md).
