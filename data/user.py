import sqlalchemy
from .db_session import SqlAlchemyBase
import datetime


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.String, autoincrement=True)
    join_date = sqlalchemy.Column(sqlalchemy.DateTime,
                                  default=datetime.datetime.now)
    warns = sqlalchemy.Column(sqlalchemy.Integer, default=0)
    messages = sqlalchemy.Column(sqlalchemy.Integer, nullable=True, default=0)

    def warn(self):
        self.warns = self.warns + 1

    def add_message(self):
        self.messages += 1
