from flask import *
from flask import jsonify
from pymongo import MongoClient
import os, gridfs, pymongo, time, logging , sendgrid
from werkzeug import secure_filename
from random import randint

app=Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'upload/'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
db_conn=None

# login doesn't happen yet
@app.route('/login')
def login():
    abort(401)
    #this_is_never_executed()

# route to the root directory
@app.route('/')
def home():
	if not os.path.exists('upload/'):
		try:
			os.makedirs('upload/')
		except Exception as e:
			logger.info( e )
	return render_template('index.html')

# safety function to get a connection to the db above
def get_db():
	try:
		logger.info( "Connecting to db ..." + str(db_conn) )
	except Exception as e:
		db_conn=None
	if not db_conn:
		try:
			uri = os.environ.get('MONGOLAB_URI', 'mongodb://localhost')
            		conn = MongoClient(uri)
            		db = conn.heroku_app33243434
            		db_conn = db
        	except pymongo.errors.ConnectionFailure, e:
            		logger.critical("Could not connect to MongoDB: %s" % e)
    	return db_conn

# returns if space is taken
def search_file(room_number):
    db_conn = get_db()
    try:
        return db_conn.fs.files.find_one(dict(room = room_number))
    except Exception:
        return False

#find an integer not currently taken in db
def find_number():
	db_conn = get_db()
	'''
	The empty dict in the first argument means "give me every document in the database"
	The "fields=['room']" in the second argument says "of those documents, only populate the
 	'room' field." This is to cut down on the size of your response. The list comprehension pulls
	the value from the "room" field from each dict in the list of dicts returned by find().
	'''
	rooms_in_db = [doc["room"] for doc in db_conn.fs.files.find({}, fields=["room"])]
	room_not_in_db = int(max(rooms_in_db)) + 1
	return room_not_in_db


# put files in mongodb
def insert_file(file_name, room_number):
	if not(file_name and room_number):
		return
	db_conn = get_db()
	gfs = gridfs.GridFS(db_conn)
	if search_file(room_number):
		logger.info( "Space :"+ str(room_number) + ' is taken!' )
		return False
	try:
		with open('upload/' + file_name, "r") as f:
			#write bytes of the file into the gfs database
			gfs.put(f, room=room_number, name=file_name)
		logger.info( "Stored file : "+str(room_number)+' Successfully')
		return True
	except Exception as e:
		logger.info( "File :"+'upload/'+file_name+" probably doesn't exist, : "+str(e) )
		return False

# remove files from mongodb
def delete_file(room_number):
	if not(room_number):
		raise Exception("delete_file given None")
	if not search_file(room_number):
		logger.info( "File "+str(room_number)+' not in db, error?' )
		return True
	db_conn = get_db()
	gfs = gridfs.GridFS(db_conn)
	_id = db_conn.fs.files.find_one(dict(room=room_number))['_id']
	gfs.delete(_id)
	logger.info( "Deleted file :"+str(room_number)+' Successfully' )
	return True

# read files from mongodb
def extract_file(output_location, room_number):
	if not(output_location and room_number):
		raise Exception("extract_file not given proper values")
	if not search_file(room_number):
		logger.info( "File "+str(room_number)+' not in db, error?' )
		return False
	db_conn = get_db()
	gfs = gridfs.GridFS(db_conn)
	try:
		_id = db_conn.fs.files.find_one(dict(room=room_number))['_id']
		file_name = db_conn.fs.files.find_one(dict(room=room_number))['name']
		with open('upload/' + file_name , 'w') as f:
			f.write(gfs.get(_id).read())
		gfs.get(_id).read() # not sure why this line is here.
		logger.info( "Written file :"+str(room_number)+' Successfully' )
		return True
	except Exception as e:
		logger.info( "failed to read file :"+str(e) )
		return False

#upload routine
@app.route('/upload',methods=['POST'])
def upload():
	#get the form inputs
	file = request.files['file']
	space = request.form['space']
	# if file and space are given
	if file and space:
		# search to see if number is taken
		if search_file(space):
			#space is taken, generate new available number
			new = find_number()
			return render_template('index.html', space=space, new=new)
		#make the file safe, remove unsupported chars
		filename = secure_filename(file.filename)
		logger.info('Securing Filename: '+filename)
		#move the file to our upload folder
		file.save(os.path.join(app.config['UPLOAD_FOLDER'],filename))
		logger.info('File '+filename+' saved.')
		# save file to mongodb
		res = insert_file(filename,space)
		logger.info('Inserted '+ filename +' to db at position: '+str(space) )
		# upload failed for whatever reason
		if not res:
			os.unlink(os.path.join( app.config['UPLOAD_FOLDER'] , filename ))
			return render_template('index.html', space=space, failed=True)
		if app.debug:
			# debugging lines to write a record of inserts
			with open('debug.txt', 'w') as f:
				f.write('File name is : '+filename+', and the space is : '+ str(space) )
		# file upload successful, remove copy from disk.
		os.unlink(os.path.join( app.config['UPLOAD_FOLDER'] ,  filename  ))
		return render_template('index.html', space=space, upload=True)
	else: # something went wrong then! yes, indeed,
		return render_template('error.html')
	@after_this_request
	def expire_file():
		logger.info("AFTER REQUEST HAPPENING.")
		# wait 10 minutes,
		time.sleep(600)
		delete_file(space)
		try:  #attempt to unlink just in case.
			os.unlink(os.path.join( app.config['UPLOAD_FOLDER'], filename))
		except Exception:
			return
		return

# download routine
@app.route( '/upload/<spacenum>' , methods=['GET'])
def download(spacenum):
	logger.info("Entering server redirect!")
	# check it's in there
	if not search_file(spacenum):
		logger.info( "File "+str(spacenum)+' not in db, error?' )
        # return error or 404, or something, we have no file.
        return render_template('index.html', undef=True, space=spacenum)
	# render the template
	render_template('index.html' , spacenum = spacenum)
	logger.info("Connecting to DB")
	# connect to mongo
	db_conn = get_db()
	gfs = gridfs.GridFS(db_conn)
	file_name = db_conn.fs.files.find_one(dict(room=spacenum))['name']
	logger.info("File name is : "  +file_name + " !")
	#extract file to send from directory
	extract_file(app.config['UPLOAD_FOLDER'] , spacenum )
	# send the file we just created
	response = send_file(app.config['UPLOAD_FOLDER']+file_name)
	return response
	@after_this_request
	def clean_file(response):
		# clean the file after it's served.
		logger.info( 'Response is : '+response)
		os.unlink(os.path.join( app.config['UPLOAD_FOLDER'] , file_name  ))
		return

# Route that will process the AJAX request,
# result as a proper JSON response with a currently free int in the database
@app.route('/_find_number')
def find_number_request():
    unused = 0
    try:
        unused = find_number()
    except Exception as e:
        #logger.info("error on JSON request: "+str(e))
        logger.info("shit's gone downhill fast")
        return jsonify(result=64)
    print("Returning : "+ str(unused))
    return jsonify(result=unused)

# page not found
@app.errorhandler(404)
def new_page(error):
	return render_template('error.html', error=404)

# method not allowed
@app.errorhandler(405)
def new_page(error):
	return render_template('error.html', error=405)

# Internal Server Error
@app.errorhandler(500)
def page_not_found(error): # will send me an email with hopefully some relevant information using sendgrid
	sg = sendgrid.SendGridClient('YOUR_SENDGRID_USERNAME', 'YOUR_SENDGRID_PASSWORD')
	message = sendgrid.Mail()
	message.add_to('David Awad <davidawad64@gmail.com>')
	message.set_subject('500 Error on Spaceshare')
	message.set_html('')
	message.set_text('Hey dave, there was another error on spaceshare I apologize! Spaceshare currently has visitors, so get on dat.')
	message.set_from('Space Admin <Admin@spaceshare.me>')
	#status, msg = sg.send(message)
	return render_template('error.html', error=500)


if __name__ == '__main__':
	app.run(debug=True)
