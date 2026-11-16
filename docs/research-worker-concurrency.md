# Two research workers

The research service defaults to one worker. To use two, set
`GAMBIT_RESEARCH_WORKERS=2` for the service. Leave one coordinator per
workspace. The coordinator retains the existing executor lock and assigns
unique requests in queue order. Only frozen individual FX price-return jobs
for distinct instruments run concurrently. Other jobs use one lane.

Each subprocess uses a bounded, private cache and revalidates the existing
input witnesses. A shared lock covers verified Feature catalog reads and an
exclusive lock covers Feature publication. The native writer, lineage index
and research record checks still apply. On a normal stop the service stops
claiming work and drains both requests. systemd should signal the coordinator
first (`KillMode=mixed`) and allow it to drain (`TimeoutStopSec=infinity`).

Before activating with an accepted queue, verify the same frozen scientific
implementation and compare saved closures from one and two workers sharing
the same isolated store on the deployment platform. This does not authorize
changing a frozen research envelope or moving it to another implementation.
Review the exact worker-only release under the standard backup and maintenance
locks, drain the current request, and restart the worker with the new setting.
Monitor worker health, both request IDs in the service heartbeat, queue
progress, memory, and the web and paper-trading services.

To return to one worker, drain the coordinator, remove the parallel setting
and restart the service. Successful trials and queued requests stay in the
same store.
