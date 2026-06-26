from ib_insync import TagValue, Order

try:
    order = Order()
    order.algoStrategy = "Adaptive"
    # Testing if we can assign a list of tuples vs TagValue
    params = [("adaptivePriority", "Patient")]
    # The error usually happens during serialization when ib_insync expects .tag
    for p in params:
        print(f"Testing tuple: {p}")
        try:
            # Fake logic similar to what ib_insync might do
            print(f"Accessing .tag: {p.tag}")
        except AttributeError:
            print("Caught expected AttributeError: tuple has no attribute 'tag'")
            
    # Now testing TagValue
    params_correct = [TagValue("adaptivePriority", "Patient")]
    for p in params_correct:
        print(f"Testing TagValue: {p}")
        print(f"Accessing .tag: {p.tag}")
        print(f"Accessing .value: {p.value}")

except Exception as e:
    print(f"Error: {e}")
