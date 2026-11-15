# Recordly — design review, not an app release

The uploaded Design & UX Improvement Audit is reference material, not a requirement to implement every unchecked box.

## Review scope

- Start from the current application's actual React components, current brand asset, local fonts and styles.
- Keep the original extraction intact as `Current`. Make visual/interaction proposals only in the refined copy.
- All records are fictional and memory-only. No sign-in, Drive access, native execution, real document generation, storage cleanup or application update is performed.
- The main Recordly artifact, desktop services, configuration formats and native code must remain unchanged until the user approves.

## Accept for design preview

1. Clearer editor hierarchy, inclusion labels, long-name handling, output previews and navigation. Remove prominent technical limits; keep actual validation.
2. Explain local save and Drive sync independently, with actionable offline/error states. Avoid repeating the same error in multiple cards.
3. Add useful subject/program search/filtering, selection explanations and actionable missing-content reasons, while preserving explicit selection, including an empty selection.
4. Use friendly saved-version display names while retaining real filenames in details. Clarify that Save as saves a copy, and show the Microsoft Word dependency before PDF export.
5. Improve configuration review and safe cleanup/restore confirmations. Present actual supported subject-configuration semantics, not the audit's hypothetical multi-subject merge.
6. Consistent spacing, focus states, text contrast, long-name handling and narrow-window layouts.

## Keep existing behaviour

- Current colours, logo and serif/sans typography.
- Save Now means local save followed by Drive sync.
- Three-minute Drive sync and mandatory successful sync before closing.
- Template-driven fields, required-field generation checks and existing per-field font options.
- Explicit generation choices belong to the workspace, not whichever program was last opened.
- Generated documents use a frozen snapshot and do not prevent further editing.
- Only one active computer, with existing reviewed Local/Drive conflict recovery.
- Recoverable Trash; no permanent deletion.

## Do not add just for this audit

- Dashboard totals, completion percentages AND remaining counts all displaying the same information.
- Decorative gradients, new illustrations, large shadows or entrance animations.
- A full IDE, compiler/execution UI, heavyweight editor dependency, autocomplete or rich-text output.
- New analytics, account modes, merge policies, storage formats or changed generation semantics.
- Additional normal-use diagnostics panels or an always-visible technical status console.

## Verify rather than infer

The audit's Java/Python titles may be screenshot/sample data, not a relationship bug. Existing runtime counts enumerate tracked objects, not verified pending uploads. The prototype can clarify that wording, but it is not evidence that native sync or persisted student data has been fixed.

Existing code already contains local/Drive separation, dynamic generation labels, explicit selection persistence, frozen-snapshot messaging and draft guards. Improve discoverability instead of duplicating those features.

## Review instructions

Compare Current and Refined on the canvas. Use the navigation and sample editor; edits affect only the individual preview's memory. Reload to reset. Open Settings, Documents, Trash and configuration import to review secondary states. Approval of a preview is required before a separate production integration.
