from flask import Flask, render_template, request, abort, redirect, session, Response

from flask.ext.httpauth import HTTPDigestAuth
import os
import json
import zipfile
from werkzeug import secure_filename
from functools import wraps


app = Flask(__name__)
root = os.path.dirname(os.path.abspath(__file__))

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'js', 'css', 'zip'])

try:
    with open(os.path.join(root, 'config.json')) as x:
        config = json.loads(x.read())
        app.config['SECRET_KEY'] = str(config['secret_key'])
        users = {config['admin_username']: config['admin_pass']}
except Exception, e:
    app.config['SECRET_KEY'] = '0000000000'
    users = {}


''' USER AUTHENTICATION '''

auth = HTTPDigestAuth()

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None

# def check_auth(username, password):
#     """This function is called to check if a username /
#     password combination is valid.
#     """
#     if 'ADMIN_USERNAME' not in app.config or 'ADMIN_PASS' not in app.config:
#         return False
#     return username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASS']


# def authenticate():
#     """Sends a 401 response that enables basic auth"""
#     return Response(
#         'Could not verify your access level for that URL.\n'
#         'You have to login with proper credentials', 401,
#         {'WWW-Authenticate': 'Basic realm="Login Required"'})


# def auth.login_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         auth = request.authorization
#         if not auth or not check_auth(auth.username, auth.password):
#             return authenticate()
#         return f(*args, **kwargs)
#     return decorated


''' FILE UPLOADS '''


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


def unzip(zipFilePath, destDir):
    zfile = zipfile.ZipFile(zipFilePath)
    for name in zfile.namelist():
        (dirName, fileName) = os.path.split(name)
        if fileName == '':
            # directory
            newDir = destDir + '/' + dirName
            if not os.path.exists(newDir):
                os.mkdir(newDir)
        else:
            # file
            fd = open(destDir + '/' + name, 'wb')
            fd.write(zfile.read(name))
            fd.close()
    zfile.close()

''' Directory Crawler '''


def dircrawl(directory, rootdir=None):
    if rootdir is None:
        directory = os.path.join(root, directory)
        rootdir = directory
        if not rootdir.endswith('/'):
            rootdir += '/'
    tree = dict(path=directory.replace(rootdir, '', 1), name=os.path.basename(directory))
    try:
        files = sorted(os.listdir(directory))
    except OSError:
        pass
    else:
        if len(files) > 0:
            tree['children'] = []
        for item in files:
            thisfile = os.path.join(directory, item)
            tree['children'].append(dircrawl(thisfile, rootdir))
    return tree


''' ADMIN VIEWS '''


@app.route('/admin/config', methods=['GET', 'POST'])
def configure():
    # Don't come here if we've configured already
    global users
    if len(users) > 0:
        return redirect('/admin')
    formdata = {'key': {'value': None, 'error': None},
                'username': {'value': None, 'error': None},
                'password': {'value': None, 'error': None},
                'password2': {'value': None, 'error': None},
                }
    if request.method == 'POST':
        for key, value in formdata.iteritems():
            value['value'] = request.form[key]
            if request.form[key] == "":
                value['error'] = "This field is required."
        # Verify the data
        if len(formdata['key']['value']) <= 10:
            formdata['key']['error'] = "Key length should be greater than 10."
        if formdata['password']['value'] != formdata['password2']['value']:
            formdata['password']['value'], formdata['password2']['value'] = None, None
            formdata['password']['error'] = "Passwords don't match."
        if len([1 for key, value in formdata.iteritems() if value['error'] is not None]) == 0:
            # Everything's OK! Let's configure!
            configuration = {'secret_key': formdata['key']['value'],
                             'admin_username': formdata['username']['value'],
                             'admin_pass': formdata['password']['value']}
            with open(os.path.join(root, 'config.json'), 'w') as x:
                x.write(json.dumps(configuration))
            app.config.update(
                SECRET_KEY=str(formdata['key']['value']),
            )
            
            users = {formdata['username']['value']: formdata['password']['value']}
            return redirect('/admin')

    return render_template('admin/config.html', formdata=formdata)



@app.route('/admin/upload', methods=['POST'])
@auth.login_required
def upload_file():
    if request.method == 'POST':
        uploadpath = request.form['uploadpath']
        file = request.files['uploadfile']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(root, 'static/custom/', uploadpath, filename)
            if not os.path.exists(os.path.dirname(filepath)):
                os.makedirs(os.path.dirname(filepath))
            file.save(filepath)
            # Unzip the file if it's a zipfile
            if filepath.endswith('.zip') and zipfile.is_zipfile(filepath):
                unzip(filepath, os.path.dirname(filepath))
                os.remove(filepath)
            return redirect('/admin')
    abort(500)


@app.route('/admin')
@auth.login_required
def admin():
    # Get all current pages
    systempages = [('Base Template', 'base.html'), ('Homepage', 'home.html'), ('Skeleton', 'skeleton.html'), ('404 Page', '404.html'), ('500 Page', '500.html')]
    pages = dircrawl('templates/custom/pages')
    staticfiles = dircrawl('static/custom')
    return render_template('admin/admin.html', systempages=systempages, pages=pages, staticfiles=staticfiles)


@app.route('/admin/<scope>/<function>/<path:page>', methods=['GET', 'POST'])
@auth.login_required
def adminfunction(scope, function, page):
    if scope == "page":
        base = 'templates/custom/'
    elif scope == "static":
        base = 'static/custom/'
    else:
        abort(404)

    path = os.path.join(root, '%s%s' % (base, page))
    if function == "edit":
        # Save file if we're posting
        if request.method == 'POST':
            if "filecontent" not in request.form:
                abort(500)
            with open(path, 'w') as x:
                    x.write(request.form['filecontent'])
                    return 'Success'
        else:
            with open(path) as x:
                    content = x.read()
            return render_template('admin/editor.html', content=content, page=page, scope=scope)

    elif function == "delete":
        if path.startswith(os.path.join(root, 'templates/custom/pages')) or path.startswith(os.path.join(root, 'static/custom')):
            try:
                os.remove(path)
            except:
                os.rmdir(path)
            return redirect('/admin')
        else:
            abort(404)

    elif function == "new":
        if scope == "page":
            page = "pages/%s" % page
            path = os.path.join(root, '%s%s' % (base, page))
        if not os.path.isfile(path):
            # Create folders if they don't exist
            if not os.path.exists(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            if scope == "page":
                with open(os.path.join(root, 'templates/custom/skeleton.html')) as x:
                    content = x.read()
            elif scope == "static":
                content = ""
            with open(path, 'w') as x:
                x.write(content)
            return redirect('/admin/%s/edit/%s' % (scope, page))
        abort(404)


@app.route('/logout')
@auth.login_required
def logout():
    return Response('Successfully logged out', 401)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('custom/404.html'), 404


@app.route('/preview')
@auth.login_required
def preview():
    return render_template('custom/temp.html')


@app.route('/')
@app.route('/<path:page>')
def gotopage(page=None):
    if page is None:
        if len(users) == 0:
            # Show configuration page
            return redirect('/admin/config')
        return render_template('custom/home.html', page="home.html")
    elif page in ["home.html", "base.html", 'skeleton.html', '404.html', '500.html']:
        return render_template('custom/%s' % page, page=page)
    else:
        # Check if template exists
        if os.path.isfile(os.path.join(root, 'templates/custom/pages/%s' % page)):
            return render_template('custom/pages/%s' % page, page=page)
        else:
            abort(404)


''' Jinja Functions '''


def static(path):
    return "/static/custom/%s" % path

app.jinja_env.globals.update(static=static)
if __name__ == '__main__':
    app.run(debug=True)
