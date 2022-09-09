# Press Ctrl+F5 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import mariadb
#import sqlalchemy
#from sqlalchemy import select,func,join
#from sqlalchemy import Table, Column, Integer, String
#from sqlalchemy.ext.declarative import declarative_base
#from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://rdahlstrom:m8s3nbgsE@127.0.0.1:3306/membership_cividb'

# Test if it works
#Base = declarative_base()
#engine = sqlalchemy.create_engine(SQLALCHEMY_DATABASE_URI, echo=True)

# class Membership(Base):
#     #__table__ = Table('civicrm_membership')#, Base.metadata,
#     #                  autoload=True, autoload_with=engine)
#     __tablename__ = 'civicrm_membership'
#     id = Column(Integer, primary_key=True)
#     contact_id = Column(Integer)
#     status_id = Column(Integer)
#     def __repr__(self):
#         return f'Member: id: {self.id}, cid: {self.contact_id}, status: {self.status_id}'
#
# class Fob(Base):
#     __tablename__ = 'civicrm_keyfob'
#     id = Column(Integer, primary_key=True)
#     contact_id = Column(Integer)
#     code = Column(String)
#     access_level = Column(Integer)
#
# keyfob_select = select(["civicrm_membership.id","civicrm_membership.contact_id","civicrm_membership.status_id","civicrm_keyfob.code"]).\
#                 select_from(join("civicrm_membership","civicrm_keyfob","civicrm_keyfob.contact_id=civicrm_membership.contact_id"))


def scan():

    query = "select civicrm_membership.contact_id,civicrm_membership.status_id,civicrm_keyfob.code from civicrm_keyfob join civicrm_membership on civicrm_keyfob.contact_id=civicrm_membership.contact_id order by civicrm_membership.contact_id"

    # Use a breakpoint in the code line below to debug your script.
    #DbSession = sessionmaker(bind=engine)
    #session = DbSession()
    #session.execute("select civicrm_membership.id,civicrm_membership.contact_id,civicrm_membership.status_id,civicrm_keyfob.code from civicrm_keyfob left join civicrm_membership on civicrm_keyfob.contact_id=civicrm_membership.contact_id")
    #print( session.query(Membership).filter(Membership.contact_id==3870).all() )
    #print(session.query(Membership).all()[:20])
    conn = mariadb.connect(user='rdahlstrom',password='m8s3nbgsE',
                           host='127.0.0.1',database='membership_cividb')

    cur = conn.cursor()
    #print(engine.table_names())
    cur.execute(query)
    members = {}
    member_details = ()
    memberId = None
    for contact_id, status_id, fob in cur:
        sid = int(status_id)
        cid = int(contact_id)
        if cid == memberId:
            #we've got a duplicate

            if sid < member_details[0]:
                member_details = (sid, fob)
        else:
            #new entry
            #push the last read row to the dict
            if memberId is not None:
                members[memberId] = member_details

            memberId = cid
            member_details = (sid, fob)

    if memberId is not None:
        members[memberId] = member_details

    for m in members.items():
        print(f'Member: {m[0]}, status: {m[1][0]}, fob: {m[1][1]}')

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    scan()

