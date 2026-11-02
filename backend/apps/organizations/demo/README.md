# Demo Data V1 — D1 only

`seed_demo_ranches` is an infrastructure-only command. The default and `--dry-run` perform SELECTs through a separate SQLite connection opened with `mode=ro`, `query_only`, a SQL authorizer and a read snapshot rolled back on exit. No ORM writes, seeder calls, credentials, receipts or lock files are created. `--write` always fails, even with `AGROCORE_ENABLE_DEMO_WRITES=1`. No destructive options exist.

## Configuration and execution gates

Only exact `config.settings.local` and `config.settings.demo_testing` are recognized. Production, base, the empty `testing.py` and unknown modules fail closed. No automatic settings fallback exists. The test configuration uses `:memory:` to prevent Django from touching the application database; tests create their own temporary SQLite fixture files. Runtime preflight refuses memory databases.

A trusted settings configuration must explicitly provide:

- `DEMO_AUTHORIZED_DATABASE`: absolute existing local SQLite file, identical to `DATABASES['default']['NAME']` after canonical validation. No remote engine, alternate alias, host, port, connection options, URI, UNC, symlink, junction/reparse point, hard link or ambiguous path is accepted. Windows requires a fixed drive. D1 rejects WAL databases rather than modifying journal mode or creating shared-memory sidecars.
- `DEMO_PROTECTED_ORGANIZATION_UUID`: UUID of the existing Rancho los Hermanos organization. It must resolve to that exact organization name (case-insensitive), and can never be a demo UUID. No discovery/adoption by similar name is performed.
- `DEMO_CATALOG_BINDINGS`: explicit UUIDs keyed by `catalog_species`, `catalog_breeds`, `catalog_weighing_methods`, `catalog_breeding_types`. Active rows and species/breed coherence are checked. Required active codes are RANCH, F, M, ACTIVE, SOLD, TRANSFER, SALE and MILK. Additional scenarios require additional approved bindings in D2-D4. Missing prerequisites return blockers and a failing command status, without changing them.
- When inspecting a receipt: `DEMO_MANIFEST_KEY`, a private verification key of at least 32 bytes, delivered outside source control. D1 does not generate this key or credentials.

The local settings currently do not authorize a path or protected UUID. Therefore a default application invocation refuses execution. Do not use the real database to exercise these guards. Tests run only disposable files. D1 did not run the command against `backend/db.sqlite3`.

## Dataset receipts and idempotency

The fixed dataset identity is `agrocore-demo-ranches-v1`, version 1, with a SHA-256 plan digest. Emails are deterministic within `demo.example.com`; organization names, codes and slugs are checked against all rows, including inactive rows. Existing emails are checked case-insensitively. Unknown collisions or an unsigned/partial dataset are rejected before adoption.

D5-FIX1 changes only the fictional email domain after verification against the real LoginSchema/UserSchema EmailStr. Existing receipts/accounts using the former domain are rejected, never migrated or updated. See D5.md for the manifest/hash implications and isolated certification results.

D6-FIX1 replaces only the first demo organization with Rancho El Encino Demo (RED01, slug rancho-el-encino-demo). Its five emails are red01.01 through red01.05 at demo.example.com. Other organizations and all quotas are unchanged. The existing Rancho El Roble (RER) is never adopted or changed. Since names/codes are part of PLAN_DIGEST, old-plan receipts are rejected even with valid signatures; no migration or repair exists. The livestock plan uses exact BOV/HOL catalog bindings and MILK/L, with SCALE and NAT supplied explicitly. No catalog creation or local writer is enabled.

`--manifest` accepts an existing JSON envelope `{payload, signature}`. Signature is HMAC-SHA256 over canonical UTF-8 JSON. Payload includes dataset, version, plan digest, protected UUID, state `complete`, and inventory for every supported tenant table. Each inventory entry contains count and a digest of full sorted rows. Password hashes, if present, are hashed internally as part of receipt matching, never printed or exported by this command. The receipt itself contains no passwords, tokens or row contents.

Repeated recognized complete datasets are verified with SELECTs and produce no modifications. Changes, missing quotas, additional/cross-tenant user memberships or mismatched inventories fail closed. A valid signed receipt is not proof that all D2-D5 business rules were certified: D1 verifies provenance and equality, not the domain generation pipeline. No receipt generation command is supplied yet. No repair, password reset or partial resume exists. Losing the private receipt/key requires manual investigation; never infer ownership from prefixes.

## Concurrency and future global transaction

Windows uses an OS global named mutex derived from the canonical database path; it creates no filesystem lock. POSIX uses a nonblocking advisory lock on an existing read-only file descriptor. These locks coordinate cooperating command runs, not arbitrary external applications. Acquiring or inspecting a mutex failure stops execution; release occurs on exceptions. D1 uses only a read snapshot, not a write transaction.

D2 must retain the lock throughout a single `transaction.atomic(using='default')` spanning all five organizations and their complete dataset. All services must use that authorized connection; no commits by phase, no swallowed errors, no automatic retries after an uncertain commit. Failures must roll back every new record. Native service savepoints are preserved. The global **write** rollback path remains a design requirement, not implemented or certified by D1.

Before D2 writes are enabled: establish trusted filesystem permissions, backup and protected-row snapshots; recheck identity/schema/catalogs under the lock; constrain all writes/FKs to newly created UUIDs; retain existing validators and schemas; assert quotas and protected-data equality before commit. Filesystem checks reduce accidental redirection but do not defend against a privileged actor swapping paths concurrently. No live data migrations or catalog repairs are allowed as part of the seeder.

## Credentials and crash recovery strategy (not executable in D1)

D2 will generate one cryptographically random password per new account, validate it with Django, and use create_user/set_password. No fixed password, CLI password argument, stdout credential, token generation or email delivery. Accounts have one default active membership and no staff/superuser privileges.

Credential delivery requires a pre-created, access-restricted directory outside the repository (Windows ACL for the invoking user; POSIX 0600 files), exclusive staged-file creation and no overwrite. Generate credentials and dataset identity into a protected pending bundle before database commit, without logging contents. Bind bundle/receipt to the dataset identity and protected UUID. Publish by atomic rename only after commit. If publication fails, preserve the pending bundle and report only the failure and recovery location. A subsequent recovery must verify the committed dataset before publishing; never regenerate passwords or reseed. If commit rolled back, do not label pending credentials usable. Protect the signing key separately from the receipt.

SQL and filesystem commits are not jointly atomic. D2 needs fault-injection tests for failed staging, rollback, failed rename, crash after commit and concurrent recovery before enabling any writer.

## Validation

Run only:

```
python -B manage.py test apps.organizations.tests_demo_d1 --settings=config.settings.demo_testing
python -B manage.py check --settings=config.settings.demo_testing
```

Tests are SimpleTestCase with ORM database access forbidden. Fixture creation/mutation is restricted to TemporaryDirectory files and does not execute migrations. D1 security tests do not certify D2-D5.
