-- Model assignment identity changed from detector-only keys to stable
-- capability + Rail bindings. Reusing the old revision JSON would make Input
-- and Output appear configured while the Runner receives no valid binding.
-- Provider credentials and registered Models remain intact; administrators
-- explicitly validate and activate the new binding revision in the UI.
DELETE FROM "model_configuration_revision";
