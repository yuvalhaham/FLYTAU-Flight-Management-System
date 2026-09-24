CREATE DATABASE IF NOT EXISTS FLYTAU;
USE FLYTAU;

-- 1. מטוס (Plane)
CREATE TABLE Plane (
    PlaneID VARCHAR(45) NOT NULL,
    PlaneSize VARCHAR(45),
    Manufacturer VARCHAR(45),
    PurchaseDate DATE,
    PRIMARY KEY (PlaneID)
);

-- 2. מחלקה (Class)
CREATE TABLE Class (
    PlaneID VARCHAR(45) NOT NULL,
    ClassType VARCHAR(45) NOT NULL,
    NumRows INT,
    NumCols INT,
    PRIMARY KEY (PlaneID, ClassType),
    FOREIGN KEY (PlaneID) REFERENCES Plane(PlaneID)
);

-- 3. מנהלים (Managers)
CREATE TABLE Managers (
    ManagerID INT NOT NULL,
    StartDate DATE,
    Phone VARCHAR(45),
    FirstName VARCHAR(45),
    LastName VARCHAR(45),
    City VARCHAR(45),
    Street VARCHAR(45),
    HouseNumber INT,
    M_Password VARCHAR(45),
    PRIMARY KEY (ManagerID)
);

-- 4. טייסים (Pilots)
CREATE TABLE Pilots (
    PilotID INT NOT NULL,
    StartDate DATE,
    Phone VARCHAR(45),
    FirstName VARCHAR(45),
    LastName VARCHAR(45),
    City VARCHAR(45),
    Street VARCHAR(45),
    HouseNumber INT,
    TrainingPassed BOOLEAN,
    PRIMARY KEY (PilotID)
);

-- 5. דיילים (FlightAttendants)
CREATE TABLE FlightAttendants (
    AttendantID INT NOT NULL,
    StartDate DATE,
    Phone VARCHAR(45),
    FirstName VARCHAR(45),
    LastName VARCHAR(45),
    City VARCHAR(45),
    Street VARCHAR(45),
    HouseNumber INT,
    TrainingPassed BOOLEAN,
    PRIMARY KEY (AttendantID)
);

-- 6. לקוחות אורחים
CREATE TABLE GuestCustomers (
    GuestEmail VARCHAR(45) NOT NULL,
    FirstName VARCHAR(45),
    LastName VARCHAR(45),
    PRIMARY KEY (GuestEmail)
);

CREATE TABLE GuestPhones (
    GuestEmail VARCHAR(45) NOT NULL,
    PhoneNumber VARCHAR(45) NOT NULL,
    PRIMARY KEY (GuestEmail, PhoneNumber),
    FOREIGN KEY (GuestEmail) REFERENCES GuestCustomers(GuestEmail)
);

-- 7. לקוחות רשומים
CREATE TABLE RegisteredCustomers (
    RegEmail VARCHAR(45) NOT NULL,
    FirstName VARCHAR(45),
    LastName VARCHAR(45),
    RegistrationDate DATE,
    PassportNumber VARCHAR(45),
    R_Password VARCHAR(45),
    BirthDate DATE,
    PRIMARY KEY (RegEmail)
);

CREATE TABLE RegisteredPhones (
    RegEmail VARCHAR(45) NOT NULL,
    PhoneNumber VARCHAR(45) NOT NULL,
    PRIMARY KEY (RegEmail, PhoneNumber),
    FOREIGN KEY (RegEmail) REFERENCES RegisteredCustomers(RegEmail)
);

-- 8. מסלולים (Routes)
CREATE TABLE Routes (
    RouteID INT AUTO_INCREMENT NOT NULL,
    SourceAirport VARCHAR(45),
    DestinationAirport VARCHAR(45),
    DurationHours DOUBLE,
    PRIMARY KEY (RouteID)
);

-- 9. טיסה (Flights)
CREATE TABLE Flights (
    FlightID VARCHAR(45) NOT NULL,
    PlaneID VARCHAR(45) NOT NULL,
    RouteID INT,
    ManagerID INT,
    DepartureDate DATE,
    DepartureTime TIME,
    ArrivalDate DATE,
    ArrivalTime TIME,
    FlightType VARCHAR(45),
    FlightStatus VARCHAR(45),
    PRIMARY KEY (FlightID),
    FOREIGN KEY (PlaneID) REFERENCES Plane(PlaneID),
    FOREIGN KEY (RouteID) REFERENCES Routes(RouteID),
    FOREIGN KEY (ManagerID) REFERENCES Managers(ManagerID)
);

-- 10. מחלקות בטיסות (FlightClasses)
CREATE TABLE FlightClasses (
    FlightID VARCHAR(45) NOT NULL,
    PlaneID VARCHAR(45) NOT NULL,
    ClassType VARCHAR(45),
    TicketPrice DECIMAL(10, 2),
    PRIMARY KEY (FlightID, PlaneID, ClassType),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID),
    FOREIGN KEY (PlaneID, ClassType) REFERENCES Class(PlaneID, ClassType)
);

-- 11. צוות בטיסות (קשרי רבים לרבים)
CREATE TABLE FlightAttendantsInFlights (
    FlightID VARCHAR(45) NOT NULL,
    AttendantID INT NOT NULL,
    PRIMARY KEY (FlightID, AttendantID),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID),
    FOREIGN KEY (AttendantID) REFERENCES FlightAttendants(AttendantID)
);

CREATE TABLE PilotsInFlights (
    FlightID VARCHAR(45) NOT NULL,
    PilotID INT NOT NULL,
    PRIMARY KEY (FlightID, PilotID),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID),
    FOREIGN KEY (PilotID) REFERENCES Pilots(PilotID)
);

-- 12. הזמנה (Orders)
CREATE TABLE Orders (
    OrderID INT NOT NULL,
    CustomerEmail VARCHAR(45),
    CustomerType VARCHAR(45),
    FlightID VARCHAR(45),
    OrderStatus VARCHAR(45),
    OrderDate DATE,
    TotalCost DECIMAL(10, 2),
    PRIMARY KEY (OrderID),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID)
);

-- 13. כיסא בהזמנה (SeatsInOrder)
CREATE TABLE Seats (
    RowNumber INT NOT NULL,
    ColNumber INT NOT NULL,
    OrderID INT NOT NULL,
    PlaneID VARCHAR(45),
    ClassType VARCHAR(45),
    PRIMARY KEY (RowNumber, ColNumber, OrderID),
    FOREIGN KEY (OrderID) REFERENCES Orders(OrderID),
    FOREIGN KEY (PlaneID, ClassType) REFERENCES Class(PlaneID, ClassType)
);