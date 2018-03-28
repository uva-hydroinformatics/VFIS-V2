from flask import Flask, jsonify, render_template, Response, request, g, url_for, abort
import constants
import simplekml
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from passlib.apps import custom_app_context as pwd_context
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)
import json
# Set Up Flask Constants and Login
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "postgres://" + constants.user + \
    ":" + constants.password + "@" + constants.host + ":5432/postgres"
app.config['SECRET_KEY'] = 'dfjkahfjkldahfajklhdlash'
app.debug = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
auth = HTTPBasicAuth()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(64))
    first_name = db.Column(db.String())
    middle_name = db.Column(db.String())
    last_name = db.Column(db.String())
    organization = db.Column(db.String())
    title = db.Column(db.String())
    subject_areas = db.Column(db.String())
    role = db.Column(db.String())
    country = db.Column(db.String())
    state_province = db.Column(db.String())
    phone_number = db.Column(db.String())
    website = db.Column(db.String())

    def hash_password(self, password):
        self.password_hash = pwd_context.encrypt(password)

    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)

    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

@auth.verify_password
def verify_password(email, password):
    # try to authenticate with username/password
    user = User.query.filter_by(email=email).first()
    if not user or not user.verify_password(password):
        return False
    g.user = user
    return True


@app.route('/api/user', methods=['POST'])
def new_user():
    userData = request.json
    password = request.json.get('password')
    if userData['access'] !=  "UVAHYDRO":
        abort(401)
    del userData['password']
    del userData['access']
    userData['role'] = "user"
    if User.query.filter_by(email=userData['email']).first() is not None:
        abort(400)    # existing user
    user = User(**request.json)
    user.hash_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"status": "OK"}), 201


@app.route('/api/user')
@auth.login_required
def get_user():
    user = User.query.get(g.user.id)
    if not user:
        abort(400)
    return jsonify(user.as_dict())


@app.route('/api/login')
@auth.login_required
def get_auth_token():
    return jsonify({"status": "OK"}), 200


class Constructions(db.Model):
    __tablename__ = 'constructions'
    fedid = db.Column(db.String, primary_key=True)
    roadname = db.Column(db.String)
    xcord = db.Column(db.Float)
    ycord = db.Column(db.Float)
    stream = db.Column(db.String)
    roadelev = db.Column(db.Float)
    forecasts = db.relationship("Forecast")


class Forecast(db.Model):
    __tablename__ = 'forecasts'
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.String)
    maxwl = db.Column(db.Float)
    floodedby = db.Column(db.Float)
    end_date = db.Column(db.String)
    construction_fed_id = db.Column(
        db.Integer, db.ForeignKey('constructions.fedid'))
    run_date_time = db.Column(db.String)


@app.route('/api/bridges/<date>')
@auth.login_required
def bridges(date):
    rows = db.session.query(Forecast.start_date, Forecast.end_date,Forecast.maxwl,Forecast.floodedby, Constructions.fedid, Constructions.roadname, Constructions.xcord, Constructions.ycord, Constructions.stream, Constructions.roadelev).join(Constructions, Forecast.construction_fed_id == Constructions.fedid).filter(Forecast.run_date_time == date).all()
    return json.dumps([row._asdict() for row in rows])


@app.route('/api/dates')
@auth.login_required
def dates():
    rows = Forecast.query.distinct(Forecast.run_date_time)
    rows = [r.run_date_time for r in rows]
    return jsonify({"dates": rows[::-1]})


@app.route('/api/kmz/<date>')
@auth.login_required
def kmz(date):
    rows = db.session.query(Forecast.start_date, Forecast.end_date,Forecast.maxwl,Forecast.floodedby, Constructions.fedid, Constructions.roadname, Constructions.xcord, Constructions.ycord, Constructions.stream, Constructions.roadelev).join(Constructions, Forecast.construction_fed_id == Constructions.fedid).filter(Forecast.run_date_time == date).all()
    ret = []
    kml = simplekml.Kml()
    kml.document.name = "Bridge locations"

    for row in rows:
        ret.append(row._asdict())

    for bridge in ret:
        xcord = bridge['xcord']
        ycord = bridge['ycord']
        roadname = bridge['roadname']
        stream = bridge['stream']
        fedid = bridge['fedid']
        roadelev = bridge['roadelev']
        MaxWL = bridge['maxwl']
        floodedby = bridge['floodedby']

        if MaxWL == -999.0:
            MaxWL = 0.0

        npo = kml.newpoint(name=roadname, coords=[(xcord, ycord)])
        npo.description = \
            "<![CDATA[<table>" \
            "<tr><td>Stream Crossed: </td><td>" + stream + "</td></tr>" \
            "<tr><td>Bridge Elevation (m): </td><td>" + str(roadelev) + "</td></tr>" \
            "<tr><td><b>Forecasted Overtopping Results from Model</b></td></tr>" \
            "<tr><td>Maximum Water Level (m):</td><td>" + str(MaxWL) + "</td></tr>" \
            "<tr><td>Bridge Overtopped by (m):</td><td>" + str(floodedby) + "</td></tr>" \
            "<tr><td>Overtopping Starting Date/Time:</td><td>" + "Coming Soon" + "</td></tr>" \
            "<tr><td>Overtopping Ending Date/Time:</td><td>" + "Coming Soon" + "</td></tr>" \
            "</table>" \
            "<img src='http://34.207.240.31/static/area_graph.png' height='100' width='300'>]]>"
        npo.style.iconstyle.icon.href = \
            'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png'

        if floodedby > 0.3:
            npo.style.iconstyle.color = simplekml.Color.red
        elif 0 < floodedby <= 0.30:
            npo.style.iconstyle.color = simplekml.Color.yellow
        else:
            npo.style.iconstyle.color = simplekml.Color.green
    filename_ = date + ".kml"
    return Response(kml.kml(), mimetype='application/kml', headers={"Content disposition": "attachment; filename=" + filename_, "Content-Type": "application/kml"})


if __name__ == "__main__":
    app.run(port=8000)
