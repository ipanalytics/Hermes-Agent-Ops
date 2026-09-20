# Question

A small team runs its own mail server on a rented VM, mostly for their own domains. They are
considering moving it home, to a box behind a reverse SSH tunnel that keeps ports 25/465/587
pointed at a cheap public VPS.

What should the migration order be, what has to be verified before the MX record changes, and
what is the rollback trigger?
