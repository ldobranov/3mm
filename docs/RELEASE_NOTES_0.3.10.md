# 3mm 0.3.10

This version carries forward the clean-install administrator fix, the read-only
application resource report and the local webhook pilot from the
[unpublished 0.3.9 candidate](RELEASE_NOTES_0.3.9.md).

- First-boot Setup assigns the initial administrator a stable subject for
  session refresh and application access. Existing accounts are unchanged.
- The resource report reads effective kernel CPU, memory and task limits.
  The installer only warns if it cannot verify memory control.
- The webhook pilot is opt-in and loopback-only; it does not enable a deployed
  public listener or automatically replay unconfirmed delivery.
- Release verification checks the health transport deadline independently of
  CI scheduling. No production timeout or health rule changed.

Keep a tested backup before upgrading. Clean-card acceptance of this exact
release on Zero W remains separate. ARMv6 Hub and Node have distinct artifacts
and catalogs. Bulgarian pack 1.0.6, Device Protocol 1.0 and Application SDK 1.3
keep their independent versions.
