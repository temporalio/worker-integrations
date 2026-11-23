// The part of smoke.py that runs inside a smoke project, next to the node_modules npm installed.
//
// Loads each module named on the command line both ways a user can: with require() from CommonJS,
// and with import() from an ES module. The two resolve package.json's `exports` with different
// conditions ("require" and "import"), so both must work. Prints one line per problem and exits
// non-zero if there were any.
import { createRequire } from 'node:module';

// Resolves from this file's folder, the smoke project, like the dynamic import() below
const require = createRequire(import.meta.url);

// Keep only an error's first line, since some errors span several (e.g. a missing module's error
// goes on to list the require stack)
const describe = (err) => String(err).split('\n')[0];

const problems = [];
for (const name of process.argv.slice(2)) {
  try {
    require(name);
  } catch (err) {
    problems.push(`require(${JSON.stringify(name)}) failed: ${describe(err)}`);
  }
  try {
    await import(name);
  } catch (err) {
    problems.push(`import(${JSON.stringify(name)}) failed: ${describe(err)}`);
  }
}
for (const problem of problems) {
  console.log(problem);
}
process.exitCode = problems.length > 0 ? 1 : 0;
