Python Bundler
==============

Simplifies virtualenv and pip usage.

Aims to be compatible with all existing projects already carrying a "requirements.txt" in their source.

Inspired by http://gembundler.com/

Howto
-----

* easy\_install pbundler
* cd into your project path
* Run pbundle. It will install your project's dependencies into a fresh virtualenv.

To run commands with the activated virtualenv:

    pbundle exec bash -c 'echo "I am activated. virtualenv: $VIRTUAL_ENV"'


Or, for python programs:

    pbundle py ./debug.py


If you don't have a requirements.txt yet but have an existing project, try this:

    pip freeze > requirements.txt


If you start fresh, try this for a project setup:

    mkdir myproject && cd myproject
    git init
    pbundle init


Instructions you can give your users:

    git clone git://github.com/you/yourproject.git
    easy_install pbundler
    pbundle


If you rather like pip, and you're sure your users already have pip:

    git clone git://github.com/you/yourproject.git
    pip install pbundler
    pbundle



Making python scripts automatically use pbundle py
--------------------------------------------------

Replace the shebang with "/usr/bin/env pbundle-py". Example:

    #!/usr/bin/env pbundle-py
    import sys
    print sys.path


WSGI/Unicorn example
--------------------

start-unicorn.sh:

    #!/bin/bash
    cd /srv/app/flaskr
    PYTHONPATH=/srv/app/wsgi exec pbundle exec gunicorn -w 5 -b 127.0.0.1:4000 -n flaskrprod flaskr:app


Custom environment variables
----------------------------

If you need to set custom ENV variables for the executed commands in your local copy, do this:

    echo "DJANGO_SETTINGS_MODULE='mysite.settings'" >> .pbundle/environment.py


TODO
----

* Build inventory from what is installed, instead of requirements.last file
* Handle failed egg installs
* Really remove all no longer needed packages from virtualenv
* Reorganize library code

