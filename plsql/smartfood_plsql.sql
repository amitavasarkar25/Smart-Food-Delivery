-- Run this script in SQL Developer as the application schema user, connected to FREEPDB1 (F5).
CREATE OR REPLACE TRIGGER trg_order_status_history
AFTER UPDATE OF order_status ON food_orders
FOR EACH ROW
WHEN (OLD.order_status <> NEW.order_status)
BEGIN
  INSERT INTO order_status_history(order_id, old_status, new_status)
  VALUES (:NEW.order_id, :OLD.order_status, :NEW.order_status);
END;
/
CREATE OR REPLACE FUNCTION fn_order_total(p_order_id IN NUMBER)
RETURN NUMBER IS v_total NUMBER(10,2);
BEGIN
  SELECT NVL(SUM(quantity * unit_price),0) INTO v_total
  FROM order_items WHERE order_id=p_order_id;
  RETURN v_total;
END;
/
CREATE OR REPLACE PROCEDURE pr_update_order_status(p_order_id IN NUMBER,p_status IN VARCHAR2)
IS
BEGIN
  IF p_status NOT IN ('PLACED','CONFIRMED','PREPARING','OUT_FOR_DELIVERY','DELIVERED','CANCELLED') THEN
    RAISE_APPLICATION_ERROR(-20001,'Invalid order status');
  END IF;
  UPDATE food_orders SET order_status=p_status WHERE order_id=p_order_id;
  IF SQL%ROWCOUNT=0 THEN RAISE_APPLICATION_ERROR(-20002,'Order not found'); END IF;
END;
/
CREATE OR REPLACE PROCEDURE pr_assign_delivery(p_order_id IN NUMBER,p_staff_id IN NUMBER)
IS
BEGIN
  UPDATE deliveries SET staff_id=p_staff_id,delivery_status='ASSIGNED'
  WHERE order_id=p_order_id AND staff_id IS NULL;
  IF SQL%ROWCOUNT=0 THEN RAISE_APPLICATION_ERROR(-20003,'Order unavailable or already assigned'); END IF;
END;
/
CREATE OR REPLACE PACKAGE pkg_smartfood AS
  FUNCTION get_order_total(p_order_id NUMBER) RETURN NUMBER;
  PROCEDURE set_status(p_order_id NUMBER,p_status VARCHAR2);
END pkg_smartfood;
/
CREATE OR REPLACE PACKAGE BODY pkg_smartfood AS
  FUNCTION get_order_total(p_order_id NUMBER) RETURN NUMBER IS
  BEGIN RETURN fn_order_total(p_order_id); END;
  PROCEDURE set_status(p_order_id NUMBER,p_status VARCHAR2) IS
  BEGIN pr_update_order_status(p_order_id,p_status); END;
END pkg_smartfood;
/
-- Explicit cursor example for coursework reporting
DECLARE
  CURSOR c_pending IS SELECT order_id, order_status, total_amount FROM food_orders WHERE order_status IN ('PLACED','CONFIRMED') ORDER BY order_id;
  v_id food_orders.order_id%TYPE; v_status food_orders.order_status%TYPE; v_total food_orders.total_amount%TYPE;
BEGIN
  OPEN c_pending;
  LOOP
    FETCH c_pending INTO v_id,v_status,v_total;
    EXIT WHEN c_pending%NOTFOUND;
    DBMS_OUTPUT.PUT_LINE('Order '||v_id||' | '||v_status||' | INR '||v_total);
  END LOOP;
  CLOSE c_pending;
END;
/
